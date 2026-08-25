"""Unit tests for inventory terminal guard (task 3.1)."""

from uuid import uuid4

import pytest
from app.modules.inventory.application.order_status import OrderStatusQuery
from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.modules.inventory.domain.entities import Inventory
from app.modules.orders.application.get_order_status import GetOrderStatus


class FakeInventoryRepository:
    def __init__(self):
        self._store = {}

    async def get_by_product(self, pid):
        inv = self._store.get(pid)
        return (
            Inventory(
                product_id=inv.product_id,
                available_quantity=inv.available_quantity,
                reserved_quantity=inv.reserved_quantity,
            )
            if inv
            else None
        )

    async def save(self, inv):
        self._store[inv.product_id] = Inventory(
            product_id=inv.product_id,
            available_quantity=inv.available_quantity,
            reserved_quantity=inv.reserved_quantity,
        )

    async def lock_and_check_availability(self, items):
        return []


class FakeOutbox:
    def __init__(self):
        self.events = []

    async def save(self, event_type, aggregate_id, payload):
        self.events.append(
            {"event_type": event_type, "aggregate_id": aggregate_id, "payload": payload}
        )

    async def get_pending(self, limit=10):
        return self.events


class FakeIdempotency:
    def __init__(self):
        self._processed = set()

    async def is_processed(self, eid, cname):
        return (eid, cname) in self._processed

    async def mark_processed(self, eid, cname):
        self._processed.add((eid, cname))


class FakeOrderStatus:
    def __init__(self, statuses):
        self._statuses = statuses
        self.calls = []

    async def get_status(self, oid):
        self.calls.append(oid)
        return self._statuses.get(oid)


class FakeOrderRepository:
    def __init__(self, orders):
        self._orders = orders

    async def get_by_id(self, oid):
        s = self._orders.get(oid)
        if s is None:
            return None

        class _O:
            def __init__(self, oid, st):
                self.id = oid
                self.status = st

        return _O(oid, s)


@pytest.mark.asyncio
async def test_get_order_status_returns_status():
    oid = uuid4()
    repo = FakeOrderRepository({oid: "confirmed"})
    q = GetOrderStatus(repo)  # type: ignore
    assert isinstance(q, OrderStatusQuery)
    assert await q.get_status(oid) == "confirmed"
    other = uuid4()
    repo2 = FakeOrderRepository({other: "cancelled"})
    q2 = GetOrderStatus(repo2)  # type: ignore
    assert await q2.get_status(other) == "cancelled"
    assert await q2.get_status(uuid4()) is None


@pytest.mark.asyncio
async def test_terminal_confirmed_skips():
    oid = uuid4()
    inv = FakeInventoryRepository()
    await inv.save(
        Inventory(product_id="p", available_quantity=10, reserved_quantity=0)
    )
    out = FakeOutbox()
    idem = FakeIdempotency()
    qs = FakeOrderStatus({oid: "confirmed"})
    uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
    eid = str(uuid4())
    await uc.execute(
        event_id=eid,
        order_id=str(oid),
        items=[{"product_id": "p", "quantity": 3}],
    )
    i = await inv.get_by_product("p")
    assert i is not None
    assert (
        i.available_quantity == 10
        and i.reserved_quantity == 0
        and out.events == []
        and len(qs.calls) == 1
    )
    assert await idem.is_processed(eid, "ProcessInventoryReservation")
    prev = len(qs.calls)
    await uc.execute(
        event_id=eid, order_id=str(oid), items=[{"product_id": "p", "quantity": 3}]
    )
    assert len(qs.calls) == prev and out.events == []


@pytest.mark.asyncio
async def test_terminal_cancelled_skips():
    oid = uuid4()
    inv = FakeInventoryRepository()
    await inv.save(
        Inventory(product_id="p", available_quantity=10, reserved_quantity=0)
    )
    out = FakeOutbox()
    idem = FakeIdempotency()
    qs = FakeOrderStatus({oid: "cancelled"})
    uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
    await uc.execute(
        event_id=str(uuid4()),
        order_id=str(oid),
        items=[{"product_id": "p", "quantity": 3}],
    )
    i = await inv.get_by_product("p")
    assert i is not None
    assert i.available_quantity == 10 and out.events == []


@pytest.mark.asyncio
async def test_duplicate_reserves_once():
    oid = uuid4()
    inv = FakeInventoryRepository()
    await inv.save(
        Inventory(product_id="p", available_quantity=10, reserved_quantity=0)
    )
    out = FakeOutbox()
    idem = FakeIdempotency()
    qs = FakeOrderStatus({oid: "pending"})
    uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
    eid = str(uuid4())
    await uc.execute(
        event_id=eid, order_id=str(oid), items=[{"product_id": "p", "quantity": 3}]
    )
    await uc.execute(
        event_id=eid, order_id=str(oid), items=[{"product_id": "p", "quantity": 3}]
    )
    i = await inv.get_by_product("p")
    assert i is not None
    assert (
        i.available_quantity == 7
        and i.reserved_quantity == 3
        and len([e for e in out.events if e["event_type"] == "InventoryReserved"]) == 1
    )


@pytest.mark.asyncio
async def test_sync_checkout_double_reserve_prevented():
    oid = uuid4()
    inv = FakeInventoryRepository()
    await inv.save(Inventory(product_id="p", available_quantity=7, reserved_quantity=3))
    out = FakeOutbox()
    idem = FakeIdempotency()
    qs = FakeOrderStatus({oid: "confirmed"})
    uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
    await uc.execute(
        event_id=str(uuid4()),
        order_id=str(oid),
        items=[{"product_id": "p", "quantity": 3}],
    )
    i = await inv.get_by_product("p")
    assert i is not None
    assert i.available_quantity == 7 and i.reserved_quantity == 3 and out.events == []


@pytest.mark.asyncio
async def test_pending_and_missing_reserve():
    for status in ["pending", None]:
        oid = uuid4()
        inv = FakeInventoryRepository()
        await inv.save(
            Inventory(product_id="p", available_quantity=10, reserved_quantity=0)
        )
        out = FakeOutbox()
        idem = FakeIdempotency()
        qs = FakeOrderStatus({oid: status} if status else {})
        uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
        await uc.execute(
            event_id=str(uuid4()),
            order_id=str(oid),
            items=[{"product_id": "p", "quantity": 3}],
        )
        i = await inv.get_by_product("p")
        assert i is not None
        assert i.available_quantity == 7 and len(out.events) == 1
    # malformed aggregate ID raises and lets consumer nack — no reservation, no status query
    inv = FakeInventoryRepository()
    await inv.save(
        Inventory(product_id="p", available_quantity=10, reserved_quantity=0)
    )
    out = FakeOutbox()
    idem = FakeIdempotency()
    qs = FakeOrderStatus({})
    uc = ProcessInventoryReservation(inv, out, idem, qs)  # type: ignore
    eid = str(uuid4())
    with pytest.raises(ValueError):
        await uc.execute(
            event_id=eid,
            order_id="order-123",
            items=[{"product_id": "p", "quantity": 3}],
        )
    i = await inv.get_by_product("p")
    assert i is not None
    assert i.available_quantity == 10 and out.events == [] and qs.calls == []
    assert not await idem.is_processed(eid, "ProcessInventoryReservation")
