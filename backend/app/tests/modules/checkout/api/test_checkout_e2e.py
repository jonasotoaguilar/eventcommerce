"""HTTP E2E scenarios for checkout idempotency and notification mapping.

Covers tasks 3.8-3.12 at the real HTTP boundary: the route, the
container, the orchestrator, and a real PostgreSQL test database.

* 3.8  a missing ``Idempotency-Key`` executes per request — two
       identical requests create two distinct orders.
* 3.9  a replay returns the cached original status/body without
       re-execution (no second reservation, order, or charge).
* 3.10 a key reused with a differing payload returns 409 and leaves the
       first execution intact (its state and its cached response).
* 3.11 concurrent duplicate requests execute exactly once and both
       clients receive the identical terminal response.
* 3.12 a notification intent exists at every terminal state, and a
       post-commit ``SendOrderNotification`` failure does not roll back
       the checkout.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Generator
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.app import create_app
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.infrastructure.models import NotificationModel
from app.modules.orders.infrastructure.models import OrderModel
from app.modules.payments.infrastructure.models import PaymentModel
from app.shared.db.session import get_db_session
from app.shared.messaging.models import OutboxEventModel, ProcessedEventModel

CHECKOUT_URL = "/api/v1/checkout"


def _valid_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "customer_id": "cus_1",
        "items": [{"product_id": "P1", "quantity": 2}],
        "amount": "19.99",
        "currency": "USD",
    }
    body.update(overrides)
    return body


def _approve_below_100(order_id: str, amount: Decimal, currency: str) -> bool:
    """Deterministic stand-in policy: amounts under 100 approve, others decline."""
    return amount < Decimal("100")


def _fail_notification(order_id: Any, channel: Any, content: Any) -> None:
    raise RuntimeError("notification channel down")


async def _seed_inventory(db_session: AsyncSession, available: int) -> None:
    repo = SqlAlchemyInventoryRepository(db_session)
    await repo.save(
        Inventory(product_id="P1", available_quantity=available, reserved_quantity=0)
    )
    await db_session.commit()


async def _count(db_session: AsyncSession, model: Any) -> int:
    result = await db_session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def _inventory_quantities(
    db_session: AsyncSession,
) -> tuple[int, int]:
    inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("P1")
    assert inventory is not None
    return inventory.available_quantity, inventory.reserved_quantity


async def _notifications_for(
    db_session: AsyncSession, order_id: UUID
) -> list[NotificationModel]:
    result = await db_session.execute(
        select(NotificationModel).where(NotificationModel.order_id == order_id)
    )
    return list(result.scalars().all())


@pytest_asyncio.fixture
async def session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture
def deterministic_payments() -> Generator[None, None, None]:
    """Swap the payment policy the container wires into AuthorizePayment.

    The container builds ``AuthorizePayment`` without an explicit policy,
    so its constructor reads the module-level ``is_payment_approved``
    default at construction time — patched here per test.
    """
    with patch(
        "app.modules.payments.application.authorize_payment.is_payment_approved",
        _approve_below_100,
    ):
        yield


@pytest.fixture
def failing_notifier() -> Generator[None, None, None]:
    """Make every SendOrderNotification.execute call fail post-commit."""
    with patch.object(
        SendOrderNotification, "execute", side_effect=RuntimeError("channel down")
    ):
        yield


class TestMissingKeyExecutesPerRequest:
    @pytest.mark.asyncio
    async def test_two_identical_requests_without_key_create_two_orders(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)

        first = await client.post(CHECKOUT_URL, json=_valid_body())
        second = await client.post(CHECKOUT_URL, json=_valid_body())

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["status"] == second.json()["status"] == "confirmed"
        assert first.json()["order_id"] != second.json()["order_id"]
        assert await _count(db_session, OrderModel) == 2
        assert await _count(db_session, ProcessedEventModel) == 0
        assert await _inventory_quantities(db_session) == (6, 4)
        assert await _count(db_session, OutboxEventModel) == 4
        assert await _count(db_session, NotificationModel) == 2
        assert await _count(db_session, PaymentModel) == 2


class TestReplayReturnsCachedResponse:
    @pytest.mark.asyncio
    async def test_identical_replay_returns_cached_201_without_reexecution(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)
        headers = {"Idempotency-Key": "replay-key"}

        first = await client.post(CHECKOUT_URL, json=_valid_body(), headers=headers)
        second = await client.post(CHECKOUT_URL, json=_valid_body(), headers=headers)

        assert first.status_code == second.status_code == 201
        assert second.json() == first.json()
        assert await _count(db_session, OrderModel) == 1
        assert await _count(db_session, PaymentModel) == 1
        assert await _inventory_quantities(db_session) == (8, 2)
        assert await _count(db_session, OutboxEventModel) == 2
        assert await _count(db_session, NotificationModel) == 1

        claims = (await db_session.execute(select(ProcessedEventModel))).scalars().all()
        assert len(claims) == 1
        assert claims[0].event_id == "replay-key"
        assert claims[0].state == "completed"
        assert claims[0].response_status == 201
        assert claims[0].response_body == first.json()


class TestKeyPayloadMismatchConflicts:
    @pytest.mark.asyncio
    async def test_mismatched_payload_returns_409_and_keeps_first_execution(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)
        headers = {"Idempotency-Key": "conflict-key"}

        first = await client.post(CHECKOUT_URL, json=_valid_body(), headers=headers)
        conflict = await client.post(
            CHECKOUT_URL, json=_valid_body(amount="9.99"), headers=headers
        )

        assert first.status_code == 201
        assert conflict.status_code == 409
        assert "different payload" in conflict.json()["detail"]
        assert await _count(db_session, OrderModel) == 1
        assert await _count(db_session, PaymentModel) == 1
        assert await _inventory_quantities(db_session) == (8, 2)
        assert await _count(db_session, OutboxEventModel) == 2

        replay = await client.post(CHECKOUT_URL, json=_valid_body(), headers=headers)
        assert replay.status_code == 201
        assert replay.json() == first.json()


class TestConcurrentDuplicates:
    @pytest.mark.asyncio
    async def test_concurrent_duplicates_execute_once_with_identical_response(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)
        headers = {"Idempotency-Key": "race-key"}

        responses = await asyncio.gather(
            client.post(CHECKOUT_URL, json=_valid_body(), headers=headers),
            client.post(CHECKOUT_URL, json=_valid_body(), headers=headers),
        )

        assert [r.status_code for r in responses] == [201, 201]
        assert responses[0].json() == responses[1].json()
        assert await _count(db_session, OrderModel) == 1
        assert await _count(db_session, PaymentModel) == 1
        assert await _inventory_quantities(db_session) == (8, 2)
        assert await _count(db_session, OutboxEventModel) == 2
        assert await _count(db_session, NotificationModel) == 1

        claims = (await db_session.execute(select(ProcessedEventModel))).scalars().all()
        assert len(claims) == 1
        assert claims[0].state == "completed"


class TestNotificationIntentAndFailure:
    @pytest.mark.asyncio
    async def test_confirmed_checkout_emits_one_notification_intent(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)

        response = await client.post(
            CHECKOUT_URL,
            json=_valid_body(),
            headers={"Idempotency-Key": "n-confirmed"},
        )

        assert response.status_code == 201
        assert response.json()["status"] == "confirmed"
        notifications = await _notifications_for(
            db_session, UUID(response.json()["order_id"])
        )
        assert len(notifications) == 1
        assert notifications[0].channel == "email"
        assert notifications[0].content == "Your order has been confirmed"

    @pytest.mark.asyncio
    async def test_insufficient_stock_cancel_emits_one_notification_intent(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 1)

        response = await client.post(
            CHECKOUT_URL,
            json=_valid_body(),
            headers={"Idempotency-Key": "n-insufficient"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["cancel_reason"] == "insufficient_stock"
        notifications = await _notifications_for(db_session, UUID(body["order_id"]))
        assert len(notifications) == 1
        assert notifications[0].channel == "email"
        assert notifications[0].content == "Your order could not be completed"

    @pytest.mark.asyncio
    async def test_payment_declined_cancel_emits_one_notification_intent(
        self, client, db_session, deterministic_payments
    ) -> None:
        await _seed_inventory(db_session, 10)

        response = await client.post(
            CHECKOUT_URL,
            json=_valid_body(amount="199.99"),
            headers={"Idempotency-Key": "n-declined"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["cancel_reason"] == "payment_declined"
        notifications = await _notifications_for(db_session, UUID(body["order_id"]))
        assert len(notifications) == 1
        assert notifications[0].channel == "email"
        assert notifications[0].content == "Your order could not be completed"

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_roll_back_checkout(
        self,
        client,
        db_session,
        deterministic_payments,
        failing_notifier,
        caplog,
    ) -> None:
        await _seed_inventory(db_session, 10)
        caplog.set_level(logging.ERROR)

        response = await client.post(
            CHECKOUT_URL,
            json=_valid_body(),
            headers={"Idempotency-Key": "nf-key"},
        )

        assert response.status_code == 201
        assert response.json()["status"] == "confirmed"
        assert await _count(db_session, OrderModel) == 1
        order = (await db_session.execute(select(OrderModel))).scalars().first()
        assert order is not None
        assert order.status == "confirmed"
        assert await _inventory_quantities(db_session) == (8, 2)
        assert await _count(db_session, PaymentModel) == 1
        assert await _count(db_session, OutboxEventModel) == 2
        assert await _count(db_session, NotificationModel) == 0
        assert any(
            "checkout_notification_failed" in record.message
            for record in caplog.records
        )
