"""Broker-free chain e2e (4.1) — fake publisher drives actual handlers.

U3 proves the full async five-state choreography:
``pending -> inventory_reserved -> payment_authorized -> confirmed`` with
the orders-owned payment-result consumer, the ``OrderPaymentAuthorized``
finalizer, and inventory compensation on ``PaymentRejected``. The real
deterministic payment policy and catalog-derived totals remain the source
of truth throughout.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.catalog.domain.entities import Product
from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.modules.inventory.application.process_payment_rejected import (
    ProcessPaymentRejected,
)
from app.modules.inventory.domain.entities import Inventory
from app.modules.notifications.application.process_order_notification import (
    ProcessOrderNotification,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.orders.application.finalize_payment_authorized import (
    FinalizePaymentAuthorized,
)
from app.modules.orders.application.get_order_status import GetOrderStatus
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.application.process_payment_result import (
    ProcessOrderPaymentResult,
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


def _approved_oid(amount: str = "20.00", currency: str = "USD") -> UUID:
    for _ in range(1000):
        oid = uuid4()
        if is_payment_approved(str(oid), Decimal(amount), currency):
            return oid
    raise AssertionError("no approved order id found")


def _declined_oid(amount: str = "20.00", currency: str = "USD") -> UUID:
    for _ in range(1000):
        oid = uuid4()
        if not is_payment_approved(str(oid), Decimal(amount), currency):
            return oid
    raise AssertionError("no declined order id found")


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
    pay_result_h = ProcessOrderPaymentResult(o_repo, e_repo, outbox, idem)  # type: ignore[arg-type]
    finalizer_h = FinalizePaymentAuthorized(o_repo, e_repo, outbox, idem)  # type: ignore[arg-type]
    comp_h = ProcessPaymentRejected(inv, o_repo, idem)  # type: ignore[arg-type]
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
        "pay_result_h": pay_result_h,
        "finalizer_h": finalizer_h,
        "comp_h": comp_h,
        "notif_h": notif_h,
        "pub": _Pub(),
    }


async def _drive_to_payment_result(h, oid: UUID):  # type: ignore[no-untyped-def]
    """Drive pending -> inventory_reserved -> payment result; return ev3."""
    items = [{"product_id": "p1", "quantity": 2}]
    await h["inv_h"].execute(event_id=str(uuid4()), order_id=str(oid), items=items)
    ev1 = h["outbox"].events[0]
    assert ev1.event_type == "InventoryReserved"
    await h["pub"].publish(ev1)
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    ev2 = h["outbox"].events[1]
    assert ev2.event_type == "OrderInventoryReserved"
    await h["pub"].publish(ev2)
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    ev3 = h["outbox"].events[2]
    assert ev3.event_type in ("PaymentAuthorized", "PaymentRejected")
    await h["pub"].publish(ev3)
    return ev1, ev2, ev3


@pytest.mark.asyncio
async def test_happy_chain_pending_to_confirmed_with_terminal_notification() -> None:
    oid = _approved_oid()
    h = _h(_order(oid, "pending"), 10, 0)
    _, _, ev3 = await _drive_to_payment_result(h, oid)
    assert ev3.event_type == "PaymentAuthorized"
    assert ev3.payload == {"result": "authorized", "amount": "20.00", "currency": "USD"}
    assert h["pay_repo"].payments[0].status == "authorized"
    assert (await h["o_repo"].get_by_id(oid)).status == "inventory_reserved"  # type: ignore[union-attr]

    # Orders consumes the payment result: inventory_reserved -> payment_authorized.
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="authorized"
    )
    assert await h["idem"].is_processed(str(ev3.id), "ProcessOrderPaymentResult")
    assert len(h["outbox"].events) == 4
    ev4 = h["outbox"].events[3]
    assert (
        ev4.event_type == "OrderPaymentAuthorized"
        and ev4.payload == {"status": "payment_authorized"}
        and ev4.aggregate_id == str(oid)
    )
    assert (await h["o_repo"].get_by_id(oid)).status == "payment_authorized"  # type: ignore[union-attr]
    await h["pub"].publish(ev4)
    # Duplicate payment-result delivery emits nothing more.
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="authorized"
    )
    assert len(h["outbox"].events) == 4

    # Finalizer confirms exactly once and emits the terminal event.
    await h["finalizer_h"].execute(event_id=str(ev4.id), order_id=oid)
    assert await h["idem"].is_processed(str(ev4.id), "FinalizePaymentAuthorized")
    assert len(h["outbox"].events) == 5
    ev5 = h["outbox"].events[4]
    assert (
        ev5.event_type == "OrderConfirmed"
        and ev5.payload == {"status": "confirmed"}
        and ev5.aggregate_id == str(oid)
    )
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    await h["pub"].publish(ev5)
    await h["finalizer_h"].execute(event_id=str(ev4.id), order_id=oid)
    assert len(h["outbox"].events) == 5

    # Terminal event drives exactly one notification.
    await h["notif_h"].execute(
        payload=ev5.payload,
        event_id=str(ev5.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    assert (
        len(h["n_repo"].notifications) == 1
        and h["n_repo"].notifications[0].content == "Your order has been confirmed"
    )
    await h["notif_h"].execute(
        payload=ev5.payload,
        event_id=str(ev5.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    assert len(h["n_repo"].notifications) == 1

    # Confirmed inventory stays reserved (no compensation on success).
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (8, 2)

    # Stale/conflicting late results after confirm are claimed without effect.
    eid_late = str(uuid4())
    await h["pay_result_h"].execute(event_id=eid_late, order_id=oid, result="rejected")
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    assert await h["idem"].is_processed(eid_late, "ProcessOrderPaymentResult")
    assert len(h["outbox"].events) == 5
    await h["comp_h"].execute(event_id=eid_late, order_id=oid)
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (8, 2)
    assert await h["idem"].is_processed(eid_late, "ProcessPaymentRejected")
    eid_late2 = str(uuid4())
    await h["ord_h"].execute(event_id=eid_late2, order_id=oid, result="rejected")
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    assert len(h["outbox"].events) == 5


@pytest.mark.asyncio
async def test_payment_rejection_cancels_releases_and_notifies() -> None:
    oid = _declined_oid()
    h = _h(_order(oid, "pending"), 10, 0)
    _, _, ev3 = await _drive_to_payment_result(h, oid)
    assert ev3.event_type == "PaymentRejected"
    assert ev3.payload["reason"] == "payment_declined"
    assert h["pay_repo"].payments[0].status == "declined"

    # Shared-queue fan-out order: the compensation runs while the order is
    # still staged in inventory_reserved (its strict guard), then the
    # orders side cancels with payment_declined and emits OrderCancelled.
    await h["comp_h"].execute(event_id=str(ev3.id), order_id=oid)
    assert await h["idem"].is_processed(str(ev3.id), "ProcessPaymentRejected")
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        10,
        0,
    )
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="rejected"
    )
    assert len(h["outbox"].events) == 4
    ev4 = h["outbox"].events[3]
    assert ev4.event_type == "OrderCancelled" and ev4.payload == {
        "status": "cancelled",
        "reason": "payment_declined",
    }
    order = await h["o_repo"].get_by_id(oid)
    assert order is not None and order.status == "cancelled"
    assert order.cancel_reason == "payment_declined"
    await h["pub"].publish(ev4)
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="rejected"
    )
    assert len(h["outbox"].events) == 4

    # Duplicate compensation delivery never double-releases.
    await h["comp_h"].execute(event_id=str(ev3.id), order_id=oid)
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        10,
        0,
    )
    # A fresh compensation delivery after the orders-side cancel is
    # claimed without mutating inventory (strict cancelled guard).
    eid_after_cancel = str(uuid4())
    await h["comp_h"].execute(event_id=eid_after_cancel, order_id=oid)
    assert await h["idem"].is_processed(eid_after_cancel, "ProcessPaymentRejected")
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        10,
        0,
    )
    # Compensation never mutates order status.
    assert (await h["o_repo"].get_by_id(oid)).status == "cancelled"  # type: ignore[union-attr]

    # Terminal cancellation notifies exactly once.
    await h["notif_h"].execute(
        payload=ev4.payload,
        event_id=str(ev4.id),
        event_type="OrderCancelled",
        aggregate_id=str(oid),
    )
    assert (
        len(h["n_repo"].notifications) == 1
        and h["n_repo"].notifications[0].content == "Your order could not be completed"
    )
    await h["notif_h"].execute(
        payload=ev4.payload,
        event_id=str(ev4.id),
        event_type="OrderCancelled",
        aggregate_id=str(oid),
    )
    assert len(h["n_repo"].notifications) == 1

    # A conflicting finalizer after cancel is claimed without confirming.
    eid_late = str(uuid4())
    await h["finalizer_h"].execute(event_id=eid_late, order_id=oid)
    assert (await h["o_repo"].get_by_id(oid)).status == "cancelled"  # type: ignore[union-attr]
    assert await h["idem"].is_processed(eid_late, "FinalizePaymentAuthorized")
    assert len(h["outbox"].events) == 4


@pytest.mark.asyncio
async def test_payment_missing_catalog_fails_closed_then_cancels_and_releases() -> None:
    oid = uuid4()
    h = _h(_order(oid, "pending"), 10, 0, catalog={})
    _, _, ev3 = await _drive_to_payment_result(h, oid)
    assert ev3.event_type == "PaymentRejected"
    assert ev3.payload["reason"] == "product_not_found"
    assert h["pay_repo"].payments == []

    # Compensation first (order still staged), then orders-side cancel.
    await h["comp_h"].execute(event_id=str(ev3.id), order_id=oid)
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        10,
        0,
    )
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="rejected"
    )
    ev4 = h["outbox"].events[3]
    assert ev4.event_type == "OrderCancelled"
    assert ev4.payload["reason"] == "payment_declined"
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="rejected"
    )
    await h["comp_h"].execute(event_id=str(ev3.id), order_id=oid)
    assert len(h["outbox"].events) == 4
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        10,
        0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "payment_authorized"])
async def test_stale_payment_rejected_fan_out_is_claimed_without_effect(
    status: str,
) -> None:
    """Stale PaymentRejected: neither side of the shared queue mutates."""
    oid = uuid4()
    h = _h(_order(oid, status), 8, 2)
    eid = str(uuid4())
    # Shared-queue order: compensation first, then orders-side transition.
    await h["comp_h"].execute(event_id=eid, order_id=oid)
    assert await h["idem"].is_processed(eid, "ProcessPaymentRejected")
    await h["pay_result_h"].execute(event_id=eid, order_id=oid, result="rejected")
    assert await h["idem"].is_processed(eid, "ProcessOrderPaymentResult")
    assert (await h["o_repo"].get_by_id(oid)).status == status  # type: ignore[union-attr]
    assert h["outbox"].events == []
    inv = await h["inv"].get_by_product("p1")
    assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
        8,
        2,
    )


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
    oid = _approved_oid()
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
    assert ev3.event_type == "PaymentAuthorized"
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    await h["pay_h"].execute(event_id=str(ev2.id), order_id=oid)
    assert len(h["outbox"].events) == 3
    assert len(h["pay_repo"].payments) == 1
    # Payment-result and finalizer duplicates emit nothing more.
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="authorized"
    )
    ev4 = h["outbox"].events[3]
    assert ev4.event_type == "OrderPaymentAuthorized"
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="authorized"
    )
    await h["pay_result_h"].execute(
        event_id=str(ev3.id), order_id=oid, result="authorized"
    )
    assert len(h["outbox"].events) == 4
    await h["finalizer_h"].execute(event_id=str(ev4.id), order_id=oid)
    assert h["outbox"].events[4].event_type == "OrderConfirmed"
    await h["finalizer_h"].execute(event_id=str(ev4.id), order_id=oid)
    await h["finalizer_h"].execute(event_id=str(ev4.id), order_id=oid)
    assert len(h["outbox"].events) == 5
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    # Only confirmed/cancelled are terminal: a late conflicting inventory
    # result still leaves the confirmed order untouched and is claimed.
    eid_late = str(uuid4())
    await h["ord_h"].execute(event_id=eid_late, order_id=oid, result="rejected")
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    assert await h["idem"].is_processed(eid_late, "ProcessOrderInventoryResult")
