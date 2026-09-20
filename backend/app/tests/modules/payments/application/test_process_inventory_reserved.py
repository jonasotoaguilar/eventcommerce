"""Tests for ProcessOrderInventoryReserved (U2 payment choreography).

The payment consumer derives amount/currency exclusively from authoritative
catalog products and the order's own lines, runs the existing deterministic
``AuthorizePayment``, and emits ``PaymentAuthorized``/``PaymentRejected``
through the outbox. It must never mutate order status or inventory.
"""

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.modules.catalog.domain.entities import Product
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_inventory_reserved import (
    CONSUMER_NAME,
    ProcessOrderInventoryReserved,
)
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.policy import is_payment_approved
from app.modules.payments.domain.repository import PaymentRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class FakeOrderRepository:
    """Read-only order store: save raises so order mutation is impossible."""

    def __init__(self, orders: dict[UUID, Order]) -> None:
        self._orders = dict(orders)

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def save(self, order: Order) -> None:  # pragma: no cover
        raise AssertionError("payment must never save orders")


class FakeProductRepository:
    def __init__(self, products: dict[str, Product]) -> None:
        self._products = dict(products)

    async def get_by_id(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[Product]:
        return [p for p in self._products.values() if p.active][:limit]

    async def save(self, product: Product) -> None:
        self._products[product.id] = product


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self) -> None:
        self.payments: list[Payment] = []

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        for p in self.payments:
            if p.id == payment_id:
                return p
        return None

    async def save(self, payment: Payment) -> None:
        self.payments.append(payment)


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def save(self, event_type, aggregate_id, payload) -> None:  # type: ignore[no-untyped-def]
        self.events.append(
            {"event_type": event_type, "aggregate_id": aggregate_id, "payload": payload}
        )

    async def get_pending(self, limit=100):  # type: ignore[no-untyped-def]
        return self.events[:limit]


class FakeIdempotency:
    def __init__(self) -> None:
        self._processed: set[tuple[str, str]] = set()

    async def is_processed(self, eid: str, cname: str) -> bool:
        return (eid, cname) in self._processed

    async def mark_processed(self, eid: str, cname: str) -> None:
        self._processed.add((eid, cname))


def _product(
    product_id: str, price: str = "10.00", currency: str = "USD", active: bool = True
) -> Product:
    now = datetime.now(timezone.utc)
    return Product(
        id=product_id,
        name=f"Product {product_id}",
        price=Decimal(price),
        currency=currency,
        active=active,
        created_at=now,
        updated_at=now,
    )


def _order(order_id: UUID, status: str, items: list[OrderItem]) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        id=order_id,
        customer_id="cus_1",
        status=status,
        cancel_reason=None,
        created_at=now,
        updated_at=now,
        items=items,
    )


def _harness(
    order: Order | None,
    products: dict[str, Product],
    approve: bool | None = True,
):  # type: ignore[no-untyped-def]
    payment_repo = InMemoryPaymentRepository()
    if approve is None:
        authorize = AuthorizePayment(payment_repo)
    else:
        authorize = AuthorizePayment(
            payment_repo, approval_policy=lambda o, a, c: approve
        )
    uc = ProcessOrderInventoryReserved(
        order_repo=FakeOrderRepository({order.id: order} if order else {}),
        product_repo=FakeProductRepository(products),
        authorize_payment=authorize,
        process_failure=ProcessPaymentFailure(payment_repo),
        # Narrow casts: the fakes are duck-type compatible at runtime;
        # the casts only satisfy the concrete constructor annotations.
        outbox=cast(SqlAlchemyOutboxRepository, FakeOutbox()),
        idempotency=cast(ProcessedEventStore, FakeIdempotency()),
    )
    return uc, payment_repo


class TestProcessOrderInventoryReservedHappyPath:
    @pytest.mark.asyncio
    async def test_derives_subtotal_from_catalog_and_emits_authorized(self) -> None:
        oid = uuid4()
        order = _order(
            oid,
            "inventory_reserved",
            [
                OrderItem(product_id="p1", quantity=2),
                OrderItem(product_id="p2", quantity=1),
            ],
        )
        uc, payment_repo = _harness(
            order, {"p1": _product("p1", "10.00"), "p2": _product("p2", "5.50")}
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)

        assert len(payment_repo.payments) == 1
        payment = payment_repo.payments[0]
        assert payment.status == "authorized"
        assert payment.amount == Decimal("25.50")
        assert payment.currency == "USD"
        assert payment.order_id == oid

        assert len(uc._outbox.events) == 1  # type: ignore[attr-defined]
        emitted = uc._outbox.events[0]  # type: ignore[attr-defined]
        assert emitted["event_type"] == "PaymentAuthorized"
        assert emitted["aggregate_id"] == str(oid)
        assert emitted["payload"] == {
            "result": "authorized",
            "amount": "25.50",
            "currency": "USD",
        }
        assert await uc._idempotency.is_processed(eid, CONSUMER_NAME)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_execute_takes_no_caller_amount_or_items(self) -> None:
        params = inspect.signature(ProcessOrderInventoryReserved.execute).parameters
        assert set(params) == {"self", "event_id", "order_id"}

    @pytest.mark.asyncio
    async def test_deterministic_policy_outcome_matches_derived_inputs(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=3)]
        )
        uc, payment_repo = _harness(order, {"p1": _product("p1", "7.25")}, approve=None)
        expected = is_payment_approved(str(oid), Decimal("21.75"), "USD")
        await uc.execute(event_id=str(uuid4()), order_id=oid)

        emitted = uc._outbox.events  # type: ignore[attr-defined]
        assert len(emitted) == 1
        if expected:
            assert emitted[0]["event_type"] == "PaymentAuthorized"
            assert payment_repo.payments[0].status == "authorized"
        else:
            assert emitted[0]["event_type"] == "PaymentRejected"
            assert emitted[0]["payload"]["reason"] == "payment_declined"
            assert payment_repo.payments[0].status == "declined"

    @pytest.mark.asyncio
    async def test_policy_decline_persists_declined_and_emits_rejected(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=1)]
        )
        uc, payment_repo = _harness(
            order, {"p1": _product("p1", "19.99")}, approve=False
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)

        assert len(payment_repo.payments) == 1
        assert payment_repo.payments[0].status == "declined"
        assert payment_repo.payments[0].failure_reason == "payment_declined"
        assert payment_repo.payments[0].amount == Decimal("19.99")

        assert len(uc._outbox.events) == 1  # type: ignore[attr-defined]
        emitted = uc._outbox.events[0]  # type: ignore[attr-defined]
        assert emitted["event_type"] == "PaymentRejected"
        assert emitted["payload"] == {
            "result": "rejected",
            "reason": "payment_declined",
            "amount": "19.99",
            "currency": "USD",
        }


class TestCatalogFailClosed:
    @pytest.mark.asyncio
    async def test_missing_product_rejects_without_payment_row(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="ghost", quantity=1)]
        )
        uc, payment_repo = _harness(order, {})
        await uc.execute(event_id=str(uuid4()), order_id=oid)

        assert payment_repo.payments == []
        assert len(uc._outbox.events) == 1  # type: ignore[attr-defined]
        emitted = uc._outbox.events[0]  # type: ignore[attr-defined]
        assert emitted["event_type"] == "PaymentRejected"
        assert emitted["payload"] == {
            "result": "rejected",
            "reason": "product_not_found",
            "amount": None,
            "currency": None,
        }

    @pytest.mark.asyncio
    async def test_inactive_product_rejects(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=1)]
        )
        uc, payment_repo = _harness(order, {"p1": _product("p1", active=False)})
        await uc.execute(event_id=str(uuid4()), order_id=oid)

        assert payment_repo.payments == []
        assert uc._outbox.events[0]["payload"]["reason"] == "product_inactive"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_mixed_currency_rejects(self) -> None:
        oid = uuid4()
        order = _order(
            oid,
            "inventory_reserved",
            [
                OrderItem(product_id="p1", quantity=1),
                OrderItem(product_id="p2", quantity=1),
            ],
        )
        uc, payment_repo = _harness(
            order,
            {
                "p1": _product("p1", "10.00", "USD"),
                "p2": _product("p2", "10.00", "EUR"),
            },
        )
        await uc.execute(event_id=str(uuid4()), order_id=oid)

        assert payment_repo.payments == []
        assert uc._outbox.events[0]["payload"]["reason"] == "mixed_currency"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_invalid_catalog_price_rejects(self) -> None:
        for bad_price in ("-5.00", "10.999", "0.00"):
            oid = uuid4()
            order = _order(
                oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=1)]
            )
            uc, payment_repo = _harness(order, {"p1": _product("p1", bad_price)})
            await uc.execute(event_id=str(uuid4()), order_id=oid)
            assert payment_repo.payments == []
            assert uc._outbox.events[0]["payload"]["reason"] == "invalid_catalog_data"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_invalid_quantity_rejects(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=0)]
        )
        uc, payment_repo = _harness(order, {"p1": _product("p1")})
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert payment_repo.payments == []
        assert uc._outbox.events[0]["payload"]["reason"] == "invalid_catalog_data"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_empty_lines_reject(self) -> None:
        oid = uuid4()
        order = _order(oid, "inventory_reserved", [])
        uc, payment_repo = _harness(order, {"p1": _product("p1")})
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert payment_repo.payments == []
        assert uc._outbox.events[0]["payload"]["reason"] == "invalid_order_lines"  # type: ignore[attr-defined]


class TestOrderingOwnershipAndIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_delivery_emits_once(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=1)]
        )
        uc, payment_repo = _harness(order, {"p1": _product("p1")})
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)
        await uc.execute(event_id=eid, order_id=oid)
        assert len(uc._outbox.events) == 1  # type: ignore[attr-defined]
        assert len(payment_repo.payments) == 1

    @pytest.mark.asyncio
    async def test_terminal_orders_are_skipped_and_claimed(self) -> None:
        for status in ("confirmed", "cancelled"):
            oid = uuid4()
            order = _order(oid, status, [OrderItem(product_id="p1", quantity=1)])
            uc, payment_repo = _harness(order, {"p1": _product("p1")})
            eid = str(uuid4())
            await uc.execute(event_id=eid, order_id=oid)
            assert uc._outbox.events == []  # type: ignore[attr-defined]
            assert payment_repo.payments == []
            assert await uc._idempotency.is_processed(eid, CONSUMER_NAME)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_pending_order_is_not_charged(self) -> None:
        oid = uuid4()
        order = _order(oid, "pending", [OrderItem(product_id="p1", quantity=1)])
        uc, payment_repo = _harness(order, {"p1": _product("p1")})
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)
        assert uc._outbox.events == []  # type: ignore[attr-defined]
        assert payment_repo.payments == []
        assert await uc._idempotency.is_processed(eid, CONSUMER_NAME)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_order_status_never_mutated(self) -> None:
        oid = uuid4()
        order = _order(
            oid, "inventory_reserved", [OrderItem(product_id="p1", quantity=1)]
        )
        uc, _ = _harness(order, {"p1": _product("p1")})
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert order.status == "inventory_reserved"
        assert not hasattr(uc, "_inventory_repo")
        assert not hasattr(uc, "_order_status")

    @pytest.mark.asyncio
    async def test_missing_order_raises_and_not_marked(self) -> None:
        uc, _ = _harness(None, {"p1": _product("p1")})
        oid = uuid4()
        eid = str(uuid4())
        with pytest.raises(OrderNotFoundError):
            await uc.execute(event_id=eid, order_id=oid)
        assert not await uc._idempotency.is_processed(eid, CONSUMER_NAME)  # type: ignore[attr-defined]
        assert uc._outbox.events == []  # type: ignore[attr-defined]
