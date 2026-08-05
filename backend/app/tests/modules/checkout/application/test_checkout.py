"""RED tests for the S3c1 checkout orchestrator (PostgreSQL integration).

Covers task 3.5 (happy path: pending→confirmed, authorized payment,
reserved inventory, outbox rows, notification intent), task 3.6 (payment
decline: release, cancel payment_declined, PaymentFailed persisted, no
double charge, cancellation notification), task 3.7 (insufficient stock:
cancel insufficient_stock, no approved payment, cancellation
notification), task 3.14 (one-request transaction: claim → create →
lock/reserve → authorize/persist → confirm OR release/cancel → cache →
commit → best-effort notification in a separate transaction), task 3.19
(serialize_response/hash_key helpers; no synchronous inventory-result
path), and task 3.20 (exactly one terminal order transition per request,
owned by the orchestrator; inner use cases never mutate status).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.checkout.api.schemas import CheckoutRequest
from app.modules.checkout.application.checkout import (
    CANCEL_REASON_INSUFFICIENT_STOCK,
    CANCEL_REASON_PAYMENT_DECLINED,
    Checkout,
    CheckoutResult,
)
from app.modules.checkout.application.errors import IdempotencyConflictError
from app.modules.checkout.application.helpers import hash_key, serialize_response
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.infrastructure.models import NotificationModel
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.domain.entities import Order
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.infrastructure.models import PaymentModel
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.models import OutboxEventModel
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


@pytest_asyncio.fixture
async def session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


def _request(**overrides: Any) -> CheckoutRequest:
    payload: dict[str, Any] = {
        "customer_id": "cus_1",
        "items": [{"product_id": "P1", "quantity": 2}],
        "amount": Decimal("19.99"),
        "currency": "USD",
    }
    payload.update(overrides)
    return CheckoutRequest.model_validate(payload)


def _build_checkout(session: AsyncSession, *, approve: bool = True) -> Checkout:
    payment_repo = SqlAlchemyPaymentRepository(session)
    return Checkout(
        session=session,
        order_repo=SqlAlchemyOrderRepository(session),
        create_order=CreateOrder(
            SqlAlchemyOrderRepository(session),
            SqlAlchemyEventRepository(session),
            SqlAlchemyOutboxRepository(session),
        ),
        inventory_repo=SqlAlchemyInventoryRepository(session),
        outbox=SqlAlchemyOutboxRepository(session),
        idempotency=ProcessedEventStore(session),
        authorize_payment=AuthorizePayment(
            payment_repo,
            approval_policy=lambda order_id, amount, currency: approve,
        ),
        process_payment_failure=ProcessPaymentFailure(payment_repo),
        notifier=SendOrderNotification(SqlAlchemyNotificationRepository(session)),
    )


async def _seed_inventory(session: AsyncSession, available: int) -> None:
    repo = SqlAlchemyInventoryRepository(session)
    await repo.save(
        Inventory(product_id="P1", available_quantity=available, reserved_quantity=0)
    )


async def _run_with_spies(
    session: AsyncSession,
    *,
    approve: bool,
    request: CheckoutRequest,
) -> tuple[CheckoutResult, list[Any], list[str]]:
    """Run checkout while spying ``Order.confirm`` / ``Order.cancel``.

    Plain-function spies replace the class attributes, so instance access
    still binds ``self`` and the real transitions run underneath.
    """
    confirm_calls: list[Any] = []
    cancel_calls: list[str] = []
    real_confirm = Order.confirm
    real_cancel = Order.cancel

    def spy_confirm(order: Order) -> None:
        confirm_calls.append(order.status)
        real_confirm(order)

    def spy_cancel(order: Order, reason: str) -> None:
        cancel_calls.append(reason)
        real_cancel(order, reason)

    checkout = _build_checkout(session, approve=approve)
    with (
        patch.object(Order, "confirm", spy_confirm),
        patch.object(Order, "cancel", spy_cancel),
    ):
        result = await checkout.execute(request)
    return result, confirm_calls, cancel_calls


class TestCheckoutIntegration:
    @pytest.mark.asyncio
    async def test_happy_path_confirms_order_with_reserved_inventory(
        self, db_session
    ) -> None:
        await _seed_inventory(db_session, 10)
        checkout = _build_checkout(db_session, approve=True)

        result = await checkout.execute(_request())

        assert result.status_code == 201
        body = result.body
        assert body["status"] == "confirmed"
        assert body["cancel_reason"] is None
        assert body["payment_status"] == "authorized"
        order_id = UUID(body["order_id"])

        found = await SqlAlchemyOrderRepository(db_session).get_by_id(order_id)
        assert found is not None
        assert found.status == "confirmed"

        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "authorized"
        assert payments[0].order_id == order_id

        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
        assert inventory is not None
        assert inventory.available_quantity == 8
        assert inventory.reserved_quantity == 2

        outbox = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert {row.event_type for row in outbox} == {
            "OrderCreated",
            "OrderConfirmed",
        }

        notifications = (
            (await db_session.execute(select(NotificationModel))).scalars().all()
        )
        assert len(notifications) == 1
        assert notifications[0].order_id == order_id
        assert notifications[0].channel == "email"

    @pytest.mark.asyncio
    async def test_payment_decline_releases_inventory_and_cancels_once(
        self, db_session
    ) -> None:
        await _seed_inventory(db_session, 10)
        checkout = _build_checkout(db_session, approve=False)

        result = await checkout.execute(_request())

        assert result.status_code == 201
        body = result.body
        assert body["status"] == "cancelled"
        assert body["cancel_reason"] == CANCEL_REASON_PAYMENT_DECLINED
        assert body["payment_status"] == "declined"
        order_id = UUID(body["order_id"])

        found = await SqlAlchemyOrderRepository(db_session).get_by_id(order_id)
        assert found is not None
        assert found.status == "cancelled"
        assert found.cancel_reason == CANCEL_REASON_PAYMENT_DECLINED

        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
        assert inventory is not None
        assert inventory.available_quantity == 10
        assert inventory.reserved_quantity == 0

        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "declined"
        assert payments[0].failure_reason == CANCEL_REASON_PAYMENT_DECLINED
        assert payments[0].order_id == order_id

        outbox = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert {row.event_type for row in outbox} == {
            "OrderCreated",
            "OrderCancelled",
        }
        assert (
            await db_session.execute(select(NotificationModel))
        ).scalars().first() is not None

    @pytest.mark.asyncio
    async def test_insufficient_stock_cancels_without_any_payment(
        self, db_session
    ) -> None:
        await _seed_inventory(db_session, 1)
        checkout = _build_checkout(db_session, approve=True)

        result = await checkout.execute(
            _request(items=[{"product_id": "P1", "quantity": 2}])
        )

        assert result.status_code == 201
        body = result.body
        assert body["status"] == "cancelled"
        assert body["cancel_reason"] == CANCEL_REASON_INSUFFICIENT_STOCK
        assert body["payment_status"] is None
        order_id = UUID(body["order_id"])

        found = await SqlAlchemyOrderRepository(db_session).get_by_id(order_id)
        assert found is not None
        assert found.status == "cancelled"
        assert found.cancel_reason == CANCEL_REASON_INSUFFICIENT_STOCK

        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
        assert inventory is not None
        assert inventory.available_quantity == 1
        assert inventory.reserved_quantity == 0

        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert payments == []

        outbox = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert {row.event_type for row in outbox} == {
            "OrderCreated",
            "OrderCancelled",
        }
        assert (
            await db_session.execute(select(NotificationModel))
        ).scalars().first() is not None

    @pytest.mark.asyncio
    async def test_replay_same_key_and_payload_returns_cached_response(
        self, db_session
    ) -> None:
        await _seed_inventory(db_session, 10)
        checkout = _build_checkout(db_session, approve=True)
        request = _request(idempotency_key="replay-key")

        first = await checkout.execute(request)
        second = await checkout.execute(request)

        assert second.status_code == first.status_code == 201
        assert second.body == first.body

        outbox = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert len(outbox) == 2

        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
        assert inventory is not None
        assert inventory.available_quantity == 8
        assert inventory.reserved_quantity == 2

        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert len(payments) == 1

        notifications = (
            (await db_session.execute(select(NotificationModel))).scalars().all()
        )
        assert len(notifications) == 1
        assert notifications[0].order_id == UUID(first.body["order_id"])

    @pytest.mark.asyncio
    async def test_key_reused_with_different_payload_conflicts_and_first_execution_intact(
        self, db_session
    ) -> None:
        await _seed_inventory(db_session, 10)
        checkout = _build_checkout(db_session, approve=True)

        first = await checkout.execute(_request(idempotency_key="conflict-key"))
        with pytest.raises(IdempotencyConflictError):
            await checkout.execute(
                _request(idempotency_key="conflict-key", amount=Decimal("9.99"))
            )

        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
        assert inventory is not None
        assert inventory.available_quantity == 8
        assert inventory.reserved_quantity == 2

        outbox = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert len(outbox) == 2

        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "authorized"

        replay = await checkout.execute(_request(idempotency_key="conflict-key"))
        assert replay.body == first.body
        assert replay.body["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_missing_key_executes_without_claiming(self, db_session) -> None:
        await _seed_inventory(db_session, 10)
        checkout = _build_checkout(db_session, approve=True)

        first = await checkout.execute(_request())
        second = await checkout.execute(_request())

        assert first.body["status"] == second.body["status"] == "confirmed"
        assert first.body["order_id"] != second.body["order_id"]
        orders = (await db_session.execute(select(OutboxEventModel))).scalars().all()
        assert len(orders) == 4  # OrderCreated + OrderConfirmed for each request


class TestCheckoutOwnership:
    @pytest.mark.asyncio
    async def test_happy_path_confirms_exactly_once(self, db_session) -> None:
        await _seed_inventory(db_session, 10)
        result, confirm_calls, cancel_calls = await _run_with_spies(
            db_session, approve=True, request=_request()
        )

        assert result.status_code == 201
        assert len(confirm_calls) == 1
        assert len(cancel_calls) == 0
        assert result.body["status"] == "confirmed"
        assert result.body["cancel_reason"] is None

    @pytest.mark.asyncio
    async def test_payment_declined_cancels_exactly_once(self, db_session) -> None:
        await _seed_inventory(db_session, 10)
        result, confirm_calls, cancel_calls = await _run_with_spies(
            db_session, approve=False, request=_request()
        )

        assert result.status_code == 201
        assert len(confirm_calls) == 0
        assert len(cancel_calls) == 1
        assert cancel_calls == [CANCEL_REASON_PAYMENT_DECLINED]
        assert result.body["status"] == "cancelled"
        assert result.body["cancel_reason"] == CANCEL_REASON_PAYMENT_DECLINED

    @pytest.mark.asyncio
    async def test_insufficient_stock_cancels_exactly_once(self, db_session) -> None:
        await _seed_inventory(db_session, 1)
        result, confirm_calls, cancel_calls = await _run_with_spies(
            db_session,
            approve=True,
            request=_request(items=[{"product_id": "P1", "quantity": 2}]),
        )

        assert result.status_code == 201
        assert len(confirm_calls) == 0
        assert len(cancel_calls) == 1
        assert cancel_calls == [CANCEL_REASON_INSUFFICIENT_STOCK]
        assert result.body["status"] == "cancelled"
        assert result.body["cancel_reason"] == CANCEL_REASON_INSUFFICIENT_STOCK


class TestHelpers:
    def test_serialize_response_maps_terminal_order_fields(self) -> None:
        confirmed = Order(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            customer_id="cus_1",
            status="confirmed",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
        )
        body = serialize_response(confirmed, "authorized")
        assert body == {
            "order_id": "00000000-0000-0000-0000-000000000001",
            "status": "confirmed",
            "cancel_reason": None,
            "payment_status": "authorized",
        }
        assert serialize_response(confirmed, None)["payment_status"] is None

    def test_hash_key_is_stable_short_and_distinct(self) -> None:
        assert hash_key("some-key") == hash_key("some-key")
        assert len(hash_key("some-key")) == 8
        assert hash_key("some-key") != hash_key("some-other-key")

    def test_checkout_never_references_the_amqp_inventory_result_path(self) -> None:
        from app.modules.checkout.application import checkout as checkout_module

        source = inspect.getsource(checkout_module)
        assert "process_inventory_result" not in source
        assert "ProcessOrderInventoryResult" not in source
