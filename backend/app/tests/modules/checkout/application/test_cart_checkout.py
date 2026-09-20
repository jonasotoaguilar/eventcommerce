"""U3 cart-backed checkout application tests (PostgreSQL integration).

Covers the additive cart path while keeping the inline contract green:
JWT-subject ownership, authoritative Decimal amount from live catalog
prices, active-only projection, mixed-currency rejection, empty/inactive
rejection, clear-on-confirm in the same transaction, retain-on-cancel
(stock and payment), and idempotent replay without a second order or
cart side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.domain.entities import CartLine
from app.modules.cart.infrastructure.models import CartItemModel, CartModel  # noqa: F401
from app.modules.cart.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCartRepository,
)
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.infrastructure.models import ProductModel  # noqa: F401
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.checkout.api.schemas import CheckoutRequest
from app.modules.checkout.application.checkout import (
    CANCEL_REASON_INSUFFICIENT_STOCK,
    CANCEL_REASON_PAYMENT_DECLINED,
    Checkout,
)
from app.modules.checkout.application.errors import (
    CartCurrencyMismatchError,
    CartNotFoundError,
    CartTotalExceededError,
    EmptyCartError,
    IdempotencyConflictError,
)
from app.modules.iam.infrastructure.models import UserModel  # noqa: F401
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.infrastructure.models import OrderModel  # noqa: F401
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.infrastructure.models import PaymentModel  # noqa: F401
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.models import OutboxEventModel  # noqa: F401
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

SHOPPER = UUID("11111111-1111-1111-1111-111111111111")
OTHER = UUID("22222222-2222-2222-2222-222222222222")


def _cart_request(
    cart_id: UUID, customer: UUID = SHOPPER, **over: Any
) -> CheckoutRequest:
    payload: dict[str, Any] = {
        "cart_id": str(cart_id),
        "customer_id": str(customer),
    }
    payload.update(over)
    return CheckoutRequest.model_validate(payload)


def _build(session: AsyncSession, *, approve: bool = True) -> Checkout:
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
        cart_repo=SqlAlchemyCartRepository(session),
        product_repo=SqlAlchemyProductRepository(session),
    )


async def _seed_user(session: AsyncSession, user_id: UUID) -> None:
    session.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@example.com",
            password_hash="x",
            role="shopper",
        )
    )
    await session.flush()


async def _seed_product(
    session: AsyncSession,
    product_id: str,
    price: str,
    currency: str = "USD",
    active: bool = True,
    stock: int = 10,
) -> None:
    now = datetime.now(timezone.utc)
    await SqlAlchemyProductRepository(session).save(
        Product(
            id=product_id,
            name=f"Product {product_id}",
            price=Decimal(price),
            currency=currency,
            active=active,
            created_at=now,
            updated_at=now,
        )
    )
    await SqlAlchemyInventoryRepository(session).save(
        Inventory(product_id=product_id, available_quantity=stock, reserved_quantity=0)
    )


async def _seed_cart(
    session: AsyncSession, owner: UUID, lines: list[tuple[str, int]]
) -> UUID:
    carts = SqlAlchemyCartRepository(session)
    cart = await carts.get_or_create(owner)
    for product_id, quantity in lines:
        await carts.save_line(
            CartLine(cart_id=cart.id, product_id=product_id, quantity=quantity)
        )
    await session.flush()
    return cart.id


async def _lines(session: AsyncSession, cart_id: UUID) -> list[CartLine]:
    return await SqlAlchemyCartRepository(session).list_lines(cart_id)


async def _payment_for(session: AsyncSession, order_id: UUID):
    result = await session.execute(
        select(PaymentModel).where(PaymentModel.order_id == order_id)
    )
    return result.scalar_one_or_none()


class TestCartHappyPath:
    @pytest.mark.asyncio
    async def test_derives_authoritative_amount_and_clears_cart(
        self, db_session
    ) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        await _seed_product(db_session, "p2", "5.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 2), ("p2", 1)])
        await db_session.commit()

        result = await _build(db_session, approve=True).execute(_cart_request(cart_id))

        assert result.status_code == 201
        assert result.body["status"] == "confirmed"
        order_id = UUID(result.body["order_id"])
        payment = await _payment_for(db_session, order_id)
        assert payment is not None
        assert payment.amount == Decimal("25.00")
        assert payment.currency == "USD"
        assert payment.status == "authorized"
        assert await _lines(db_session, cart_id) == []

    @pytest.mark.asyncio
    async def test_uses_live_catalog_price_not_stale_cart_total(
        self, db_session
    ) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 2)])
        await db_session.commit()

        now = datetime.now(timezone.utc)
        await SqlAlchemyProductRepository(db_session).save(
            Product(
                id="p1",
                name="Product p1",
                price=Decimal("14.50"),
                currency="USD",
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        await db_session.commit()

        result = await _build(db_session, approve=True).execute(_cart_request(cart_id))

        payment = await _payment_for(db_session, UUID(result.body["order_id"]))
        assert payment is not None
        assert payment.amount == Decimal("29.00")

    @pytest.mark.asyncio
    async def test_partially_inactive_projects_active_only(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        await _seed_product(db_session, "p2", "7.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 1), ("p2", 3)])
        await db_session.commit()

        now = datetime.now(timezone.utc)
        await SqlAlchemyProductRepository(db_session).save(
            Product(
                id="p2",
                name="Product p2",
                price=Decimal("7.00"),
                currency="USD",
                active=False,
                created_at=now,
                updated_at=now,
            )
        )
        await db_session.commit()

        result = await _build(db_session, approve=True).execute(_cart_request(cart_id))

        assert result.body["status"] == "confirmed"
        payment = await _payment_for(db_session, UUID(result.body["order_id"]))
        assert payment is not None
        assert payment.amount == Decimal("10.00")


class TestCartOwnership:
    @pytest.mark.asyncio
    async def test_missing_cart_is_404(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)

        with pytest.raises(CartNotFoundError):
            await _build(db_session).execute(_cart_request(uuid4()))

    @pytest.mark.asyncio
    async def test_other_owners_cart_is_404(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_user(db_session, OTHER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        cart_id = await _seed_cart(db_session, OTHER, [("p1", 1)])
        await db_session.commit()

        with pytest.raises(CartNotFoundError):
            await _build(db_session).execute(_cart_request(cart_id, customer=SHOPPER))

    @pytest.mark.asyncio
    async def test_non_uuid_subject_is_404(self, db_session) -> None:
        request = CheckoutRequest.model_validate(
            {"cart_id": str(uuid4()), "customer_id": "legacy-cus-1"}
        )
        with pytest.raises(CartNotFoundError):
            await _build(db_session).execute(request)


class TestCartValidation:
    @pytest.mark.asyncio
    async def test_empty_cart_is_422(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        carts = SqlAlchemyCartRepository(db_session)
        cart = await carts.get_or_create(SHOPPER)
        await db_session.commit()

        with pytest.raises(EmptyCartError):
            await _build(db_session).execute(_cart_request(cart.id))

    @pytest.mark.asyncio
    async def test_fully_inactive_cart_is_422(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", active=False, stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 1)])
        await db_session.commit()

        with pytest.raises(EmptyCartError):
            await _build(db_session).execute(_cart_request(cart_id))

    @pytest.mark.asyncio
    async def test_mixed_currencies_are_422(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "usd-item", "10.00", "USD", stock=10)
        await _seed_product(db_session, "eur-item", "8.00", "EUR", stock=10)
        cart_id = await _seed_cart(
            db_session, SHOPPER, [("usd-item", 1), ("eur-item", 1)]
        )
        await db_session.commit()

        with pytest.raises(CartCurrencyMismatchError):
            await _build(db_session).execute(_cart_request(cart_id))


class TestClearOnConfirmRetainOnCancel:
    @pytest.mark.asyncio
    async def test_insufficient_stock_cancels_and_retains_cart(
        self, db_session
    ) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=1)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 2)])
        await db_session.commit()

        result = await _build(db_session, approve=True).execute(_cart_request(cart_id))

        assert result.body["status"] == "cancelled"
        assert result.body["cancel_reason"] == CANCEL_REASON_INSUFFICIENT_STOCK
        assert [
            (line.product_id, line.quantity)
            for line in await _lines(db_session, cart_id)
        ] == [("p1", 2)]

    @pytest.mark.asyncio
    async def test_payment_decline_cancels_and_retains_cart(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 1)])
        await db_session.commit()

        result = await _build(db_session, approve=False).execute(_cart_request(cart_id))

        assert result.body["status"] == "cancelled"
        assert result.body["cancel_reason"] == CANCEL_REASON_PAYMENT_DECLINED
        assert [
            (line.product_id, line.quantity)
            for line in await _lines(db_session, cart_id)
        ] == [("p1", 1)]
        inventory = await SqlAlchemyInventoryRepository(db_session).get_by_product("p1")
        assert inventory is not None
        assert (inventory.available_quantity, inventory.reserved_quantity) == (10, 0)


class TestCartIdempotency:
    @pytest.mark.asyncio
    async def test_replay_returns_cached_without_second_order_or_clear(
        self, db_session
    ) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 2)])
        await db_session.commit()
        checkout = _build(db_session, approve=True)
        request = _cart_request(cart_id, idempotency_key="cart-replay-1")

        first = await checkout.execute(request)
        # The confirm path cleared the cart; a replay must still hit the
        # cache instead of failing on the now-empty cart.
        second = await checkout.execute(request)

        assert second.status_code == first.status_code == 201
        assert second.body == first.body
        orders = (await db_session.execute(select(OrderModel))).scalars().all()
        assert len(orders) == 1
        payments = (await db_session.execute(select(PaymentModel))).scalars().all()
        assert len(payments) == 1
        assert await _lines(db_session, cart_id) == []

    @pytest.mark.asyncio
    async def test_different_cart_id_with_same_key_conflicts(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        first_id = await _seed_cart(db_session, SHOPPER, [("p1", 1)])
        await db_session.commit()
        checkout = _build(db_session, approve=True)

        first = await checkout.execute(
            _cart_request(first_id, idempotency_key="cart-conflict-1")
        )
        assert first.body["status"] == "confirmed"

        # A different cart id under the same key is a different payload:
        # the completed claim conflicts before cart resolution runs.
        with pytest.raises(IdempotencyConflictError):
            await checkout.execute(
                _cart_request(uuid4(), idempotency_key="cart-conflict-1")
            )


class TestCartTotalCap:
    @pytest.mark.asyncio
    async def test_over_limit_derived_total_is_422_and_cart_intact(
        self, db_session
    ) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "600000000.00", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 2)])
        await db_session.commit()

        with pytest.raises(CartTotalExceededError):
            await _build(db_session, approve=True).execute(_cart_request(cart_id))

        orders = (await db_session.execute(select(OrderModel))).scalars().all()
        assert orders == []
        assert [
            (line.product_id, line.quantity)
            for line in await _lines(db_session, cart_id)
        ] == [("p1", 2)]

    @pytest.mark.asyncio
    async def test_exact_max_total_succeeds(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "999999999.99", stock=10)
        cart_id = await _seed_cart(db_session, SHOPPER, [("p1", 1)])
        await db_session.commit()

        result = await _build(db_session, approve=True).execute(_cart_request(cart_id))

        assert result.body["status"] == "confirmed"
        payment = await _payment_for(db_session, UUID(result.body["order_id"]))
        assert payment is not None
        assert payment.amount == Decimal("999999999.99")
        assert await _lines(db_session, cart_id) == []


class TestClaimReuseAfterInvalid:
    @pytest.mark.asyncio
    async def test_empty_then_filled_cart_reuses_same_key(self, db_session) -> None:
        await _seed_user(db_session, SHOPPER)
        await _seed_product(db_session, "p1", "10.00", stock=10)
        carts = SqlAlchemyCartRepository(db_session)
        cart = await carts.get_or_create(SHOPPER)
        await db_session.commit()
        checkout = _build(db_session, approve=True)
        key = "cart-reuse-after-invalid-1"

        with pytest.raises(EmptyCartError):
            await checkout.execute(_cart_request(cart.id, idempotency_key=key))

        await carts.save_line(CartLine(cart_id=cart.id, product_id="p1", quantity=1))
        await db_session.commit()

        result = await checkout.execute(_cart_request(cart.id, idempotency_key=key))

        assert result.status_code == 201
        assert result.body["status"] == "confirmed"
        orders = (await db_session.execute(select(OrderModel))).scalars().all()
        assert len(orders) == 1
