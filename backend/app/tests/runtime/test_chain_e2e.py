"""Broker-free chain e2e (4.1) — fake publisher drives actual handlers."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

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


def _h(order: Order, avail: int = 10, reserved: int = 0):  # type: ignore[no-untyped-def]
    o_repo, e_repo, outbox, idem = (
        _OrderRepo({order.id: order}),
        _EventRepo(),
        _Outbox(),
        _Idem(),
    )
    inv = _InvRepo()
    inv._s["p1"] = Inventory("p1", avail, reserved)
    n_repo = _NotifRepo()
    notifier = SendOrderNotification(n_repo)  # type: ignore[arg-type]
    get_status = GetOrderStatus(o_repo)  # type: ignore[arg-type]
    inv_h = ProcessInventoryReservation(inv, outbox, idem, get_status)  # type: ignore[arg-type]
    ord_h = ProcessOrderInventoryResult(o_repo, e_repo, outbox, idem)  # type: ignore[arg-type]
    notif_h = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    return {
        "o_repo": o_repo,
        "e_repo": e_repo,
        "outbox": outbox,
        "idem": idem,
        "inv": inv,
        "n_repo": n_repo,
        "inv_h": inv_h,
        "ord_h": ord_h,
        "notif_h": notif_h,
        "pub": _Pub(),
    }


@pytest.mark.asyncio
async def test_happy_chain_pending_to_confirmed_via_fake_publisher_with_duplicate_idempotent() -> (
    None
):
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
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert await h["idem"].is_processed(str(ev1.id), "ProcessOrderInventoryResult")
    assert len(h["outbox"].events) == 2
    ev2 = h["outbox"].events[1]
    assert (
        ev2.event_type == "OrderConfirmed"
        and ev2.payload == {"status": "confirmed"}
        and ev2.aggregate_id == str(oid)
    )
    assert (
        len(h["e_repo"].events) == 1
        and h["e_repo"].events[0]["event_type"] == "InventoryReserved"
    )
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    await h["pub"].publish(ev2)
    assert h["pub"].published[1].event_type == "OrderConfirmed"
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert len(h["outbox"].events) == 2 and len(h["e_repo"].events) == 1
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    assert await h["idem"].is_processed(str(ev2.id), "ProcessOrderNotification")
    assert len(h["n_repo"].notifications) == 1
    n = h["n_repo"].notifications[0]
    assert (
        n.channel == "email"
        and n.content == "Your order has been confirmed"
        and str(n.order_id) == str(oid)
    )
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    assert len(h["n_repo"].notifications) == 1


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
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    await h["ord_h"].execute(event_id=str(ev1.id), order_id=oid, result="reserved")
    assert len(h["outbox"].events) == 2 and len(h["e_repo"].events) == 1
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    await h["notif_h"].execute(
        payload=ev2.payload,
        event_id=str(ev2.id),
        event_type="OrderConfirmed",
        aggregate_id=str(oid),
    )
    assert len(h["n_repo"].notifications) == 1
    eid_late = str(uuid4())
    await h["ord_h"].execute(event_id=eid_late, order_id=oid, result="rejected")
    assert (await h["o_repo"].get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    assert await h["idem"].is_processed(eid_late, "ProcessOrderInventoryResult")
