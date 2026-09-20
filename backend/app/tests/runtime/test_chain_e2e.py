"""Broker-free chain e2e (4.1) — fake publisher drives actual handlers.

U2 covers the first half of the async five-state choreography:
``pending -> inventory_reserved`` (orders-owned ``OrderInventoryReserved``)
followed by catalog-derived payment authorization emitting
``PaymentAuthorized``/``PaymentRejected``. The payment-result order
transition and inventory compensation belong to U3, so the reserved path
emits no terminal ``OrderConfirmed`` and drives no notification yet.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.catalog.domain.entities import Product
from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.modules.inventory.domain.entities import Inventory
from app.modules.notifications.application.process_order_notification import (
    ProcessOrderNotification,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.orders.application.get_order_status import GetOrderStatus
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_inventory_reserved import (
    ProcessOrderInventoryReserved,
)
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.policy import is_payment_approved


class _E:
    def __init__(self, t: str, a: str, p: dict) -> None:
        self.id, self.event_type, self.aggregate_id, self.payload = uuid4(), t, a, p


class _Outbox:
    def __init__(self) -> None:
        self.events: list[_E] = []

    async def save(self, event_type: str, aggregate_id: str, payload: dict) -> None:
        self.events.append(_E(event_type, aggregate_id, payload))

    async def get_pending(self, limit: int = 100) -> list[_E]:
        return self.events[:limit]

    async def mark_published(self, event_id: UUID) -> None:  # pragma: no cover
        return


class _InvRepo:
    def __init__(self) -> None:
        self._s: dict[str, Inventory] = {}

    async def get_by_product(self, pid: str) -> Inventory | None:
        i = self._s.get(pid)
        return (
            None
            if i is None
            else Inventory(i.product_id, i.available_quantity, i.reserved_quantity)
        )

    async def save(self, inv: Inventory) -> None:
        self._s[inv.product_id] = Inventory(
            inv.product_id, inv.available_quantity, inv.reserved_quantity
        )

    async def lock_and_check_availability(self, items):  # type: ignore[no-untyped-def]
        return []


class _OrderRepo:
    def __init__(self, orders: dict[UUID, Order] | None = None) -> None:
        self._o: dict[UUID, Order] = dict(orders or {})

    async def get_by_id(self, oid: UUID) -> Order | None:
        return self._o.get(oid)

    async def save(self, o: Order) -> None:
        self._o[o.id] = o


class _ProductRepo:
    def __init__(self, products: dict[str, Product] | None = None) -> None:
        self._p: dict[str, Product] = dict(products or {})

    async def get_by_id(self, pid: str) -> Product | None:
        return self._p.get(pid)

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[Product]:
        return [p for p in self._p.values() if p.active][:limit]

    async def save(self, product: Product) -> None:
        self._p[product.id] = product


class _PayRepo:
    def __init__(self) -> None:
        self.payments: list[Payment] = []

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        for p in self.payments:
            if p.id == payment_id:
                return p
        return None

    async def save(self, payment: Payment) -> None:
        self.payments.append(payment)


class _EventRepo:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def add(
        self, event_id, aggregate_type, aggregate_id, event_type, occurred_at, payload
    ):  # type: ignore[no-untyped-def]
        self.events.append(
            {
                "event_id": event_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": payload,
            }
        )

    async def get_timeline(self, aggregate_type, aggregate_id):  # type: ignore[no-untyped-def]
        return self.events


class _Idem:
    def __init__(self) -> None:
        self._p: set[tuple[str, str]] = set()

    async def is_processed(self, eid: str, c: str) -> bool:
        return (eid, c) in self._p

    async def mark_processed(self, eid: str, c: str) -> None:
        self._p.add((eid, c))


class _NotifRepo:
    def __init__(self) -> None:
        self.notifications: list = []

    async def save(self, n) -> None:  # type: ignore[no-untyped-def]
        self.notifications.append(n)

    async def get_by_id(self, nid):  # type: ignore[no-untyped-def]
        return None


class _Pub:
    def __init__(self) -> None:
        self.published: list[_E] = []

    async def publish(self, e: _E) -> None:
        self.published.append(e)


def _product(pid: str, price: str = "10.00", currency: str = "USD") -> Product:
    now = datetime.now(timezone.utc)
    return Product(
        id=pid,
        name=f"Product {pid}",
        price=Decimal(price),
        currency=currency,
        active=True,
        created_at=now,
        updated_at=now,
    )


def _order(oid: UUID, status: str) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        id=oid,
        customer_id="cus_1",
        status=status,
        cancel_reason=None,
        created_at=now,
        updated_at=now,
        items=[OrderItem(product_id="p1", quantity=2)],
    )


def _h(
    order: Order,
    avail: int = 10,
    reserved: int = 0,
    catalog: dict[str, Product] | None = None,
):  # type: ignore[no-untyped-def]
    o_repo, e_repo, outbox, idem = (
        _OrderRepo({order.id: order}),
        _EventRepo(),
        _Outbox(),
        _Idem(),
    )
    inv = _InvRepo()
    inv._s["p1"] = Inventory("p1", avail, reserved)
    products = catalog if catalog is not None else {"p1": _product("p1")}
    prod_repo = _ProductRepo(products)
    pay_repo = _PayRepo()
    n_repo = _NotifRepo()
    notifier = SendOrderNotification(n_repo)  # type: ignore[arg-type]
    get_status = GetOrderStatus(o_repo)  # type: ignore[arg-type]
    inv_h = ProcessInventoryReservation(inv, outbox, idem, get_status)  # type: ignore[arg-type]
    ord_h = ProcessOrderInventoryResult(o_repo, e_repo, outbox, idem)  # type: ignore[arg-type]
    pay_h = ProcessOrderInventoryReserved(
        o_repo,  # type: ignore[arg-type]
        prod_repo,  # type: ignore[arg-type]
        AuthorizePayment(pay_repo),
        ProcessPaymentFailure(pay_repo),
        outbox,  # type: ignore[arg-type]
        idem,  # type: ignore[arg-type]
    )
    notif_h = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    return {
        "o_repo": o_repo,
        "e_repo": e_repo,
        "outbox": outbox,
        "idem": idem,
        "inv": inv,
        "prod_repo": prod_repo,
        "pay_repo": pay_repo,
        "n_repo": n_repo,
        "inv_h": inv_h,
        "ord_h": ord_h,
        "pay_h": pay_h,
        "notif_h": notif_h,
        "pub": _Pub(),
    }


@pytest.mark.asyncio
async def test_happy_chain_pending_to_inventory_reserved_then_payment_result() -> None:
    oid = uuid4()
    h = _h(_order(oid, "pending"), 10, 0)
    eid1, items = str(uuid4()), [{"product_id": "p1", "quantity": 2}]
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    assert await h["idem"].is_processed(eid1, "ProcessInventoryReservation")
    assert len(h["outbox"].events) == 1
    ev1 = h["outbox"].events[0]
    assert (
        ev1.event_type == "InventoryReserved"
        and ev1.aggregate_id == str(oid)
        and ev1.payload == {"items": items}
    )
    await h["pub"].publish(ev1)
    assert h["pub"].published[0].id == ev1.id and h["pub"].published[0].payload == {
        "items": items
    }
    assert "aio_pika" not in str(type(h["pub"]))
    inv = await h["inv"].get_by_product("p1")
    assert (
        inv is not None and inv.available_quantity == 8 and inv.reserved_quantity == 2
    )
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    assert len(h["outbox"].events) == 1

    # Orders stages inventory_reserved and emits the internal order-owned
    # event; payment cannot race the transition because it only reacts to it.
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert await h["idem"].is_processed(str(ev1.id), "ProcessOrderInventoryResult")
    assert len(h["outbox"].events) == 2
    ev2 = h["outbox"].events[1]
    assert (
        ev2.event_type == "OrderInventoryReserved"
        and ev2.payload == {"status": "inventory_reserved"}
        and ev2.aggregate_id == str(oid)
    )
    assert (
        len(h["e_repo"].events) == 1
        and h["e_repo"].events[0]["event_type"] == "InventoryReserved"
    )
    assert (await h["o_repo"].get_by_id(oid)).status == "inventory_reserved"  # type: ignore[union-attr]
    await h["pub"].publish(ev2)
    assert h["pub"].published[1].event_type == "OrderInventoryReserved"
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert len(h["outbox"].events) == 2 and len(h["e_repo"].events) == 1

    # Payment derives 2 x 10.00 USD from catalog and emits the deterministic
    # result; the order stays inventory_reserved (U3 owns the next hop).
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert await h["idem"].is_processed(str(ev2.id), "ProcessOrderInventoryReserved")
    assert len(h["outbox"].events) == 3
    ev3 = h["outbox"].events[2]
    expected_approved = is_payment_approved(str(oid), Decimal("20.00"), "USD")
    if expected_approved:
        assert ev3.event_type == "PaymentAuthorized"
        assert ev3.payload == {
            "result": "authorized",
            "amount": "20.00",
            "currency": "USD",
        }
        assert h["pay_repo"].payments[0].status == "authorized"
    else:
        assert ev3.event_type == "PaymentRejected"
        assert ev3.payload["reason"] == "payment_declined"
        assert h["pay_repo"].payments[0].status == "declined"
    assert ev3.aggregate_id == str(oid)
    assert (await h["o_repo"].get_by_id(oid)).status == "inventory_reserved"  # type: ignore[union-attr]
    await h["pub"].publish(ev3)
    # Duplicate payment delivery emits nothing more.
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert len(h["outbox"].events) == 3
    assert len(h["pay_repo"].payments) == 1
    # No terminal event on the reserved path: nothing notifies yet (U3).
    assert h["n_repo"].notifications == []
    assert not any(e.event_type == "OrderConfirmed" for e in h["outbox"].events)


@pytest.mark.asyncio
async def test_payment_missing_catalog_fails_closed() -> None:
    oid = uuid4()
    h = _h(_order(oid, "pending"), 10, 0, catalog={})
    eid1, items = str(uuid4()), [{"product_id": "p1", "quantity": 2}]
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    ev1 = h["outbox"].events[0]
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    ev2 = h["outbox"].events[1]
    assert ev2.event_type == "OrderInventoryReserved"

    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert len(h["outbox"].events) == 3
    ev3 = h["outbox"].events[2]
    assert ev3.event_type == "PaymentRejected"
    assert ev3.payload["reason"] == "product_not_found"
    assert h["pay_repo"].payments == []
    assert (await h["o_repo"].get_by_id(oid)).status == "inventory_reserved"  # type: ignore[union-attr]
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert len(h["outbox"].events) == 3


@pytest.mark.asyncio
async def test_rejected_chain_cancelled_via_fake_publisher_with_duplicate_idempotent() -> (
    None
):
    oid = uuid4()
    h = _h(_order(oid, "pending"), 1, 0)
    eid1, items = str(uuid4()), [{"product_id": "p1", "quantity": 2}]
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    ev1 = h["outbox"].events[0]
    assert (
        ev1.event_type == "InventoryRejected"
        and ev1.payload == {"items": items, "reason": "insufficient_stock"}
        and ev1.aggregate_id == str(oid)
    )
    await h["pub"].publish(ev1)
    assert h["pub"].published[0].event_type == "InventoryRejected"
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and inv.available_quantity == 1
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="rejected")
    ev2 = h["outbox"].events[1]
    assert ev2.event_type == "OrderCancelled" and ev2.payload == {
        "status": "cancelled",
        "reason": "insufficient_stock",
    }
    assert (await h["o_repo"].get_by_id(oid)).status == "cancelled"  # type: ignore[union-attr]
    await h["pub"].publish(ev2)
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderCancelled",
        aggregate_id=str(oid),
    )
    assert (
        len(h["n_repo"].notifications) == 1
        and h["n_repo"].notifications[0].content == "Your order could not be completed"
    )
    assert await h["idem"].is_processed(str(ev2.id), "ProcessOrderNotification")
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    assert len(h["outbox"].events) == 2
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="rejected")
    assert len(h["outbox"].events) == 2
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderCancelled",
        aggregate_id=str(oid),
    )
    assert len(h["n_repo"].notifications) == 1


@pytest.mark.asyncio
async def test_terminal_skips_reservation_and_duplicate_prevents_double_reserve() -> (
    None
):
    oid = uuid4()
    h = _h(_order(oid, "confirmed"), 7, 3)
    eid, items = str(uuid4()), [{"product_id": "p1", "quantity": 3}]
    await h["inv_h"].execute(event_id=eid, order_id=str(oid), items=items)
    inv = await h["inv"].get_by_product("p1")
    assert (
        inv is not None
        and inv.available_quantity == 7
        and inv.reserved_quantity == 3
        and h["outbox"].events == []
    )
    assert await h["idem"].is_processed(eid, "ProcessInventoryReservation")
    await h["inv_h"].execute(event_id=eid, order_id=str(oid), items=items)
    inventory = await h["inv"].get_by_product("p1")
    assert inventory is not None
    assert h["outbox"].events == [] and inventory.available_quantity == 7


@pytest.mark.asyncio
async def test_duplicate_delivery_at_each_stage_is_idempotent() -> None:
    oid = uuid4()
    h = _h(_order(oid, "pending"))
    eid1, items = str(uuid4()), [{"product_id": "p1", "quantity": 2}]
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    ev1 = h["outbox"].events[0]
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    await h["inv_h"].execute(event_id=eid1, order_id=str(oid), items=items)
    inventory = await h["inv"].get_by_product("p1")
    assert inventory is not None
    assert len(h["outbox"].events) == 1 and inventory.available_quantity == 8
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    ev2 = h["outbox"].events[1]
    assert ev2.event_type == "OrderInventoryReserved"
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert len(h["outbox"].events) == 2 and len(h["e_repo"].events) == 1
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    ev3 = h["outbox"].events[2]
    assert ev3.event_type in ("PaymentAuthorized", "PaymentRejected")
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert len(h["outbox"].events) == 3
    assert len(h["pay_repo"].payments) == 1
    # Only confirmed/cancelled are terminal: a late conflicting inventory
    # result still cancels the staged order and is claimed.
    eid_late = str(uuid4())
    await h["ord_h"].execute(event_id=eid_late, order_id=oid, result="rejected")
    assert (await h["o_repo"].get_by_id(oid)).status == "cancelled"  # type: ignore[union-attr]
    assert await h["idem"].is_processed(eid_late, "ProcessOrderInventoryResult")
