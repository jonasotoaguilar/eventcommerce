"""Unit tests for ProcessOrderInventoryResult terminal guard (task 3.2)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.errors import OrderNotFoundError


class FakeOrderRepository:
    def __init__(self, orders: dict[UUID, Order]):
        self._orders = dict(orders)
        self.save_calls = 0

    async def get_by_id(self, order_id: UUID) -> Order | None:
        o = self._orders.get(order_id)
        if o is None:
            return None
        # return same instance so status mutation visible
        return o

    async def save(self, order: Order) -> None:
        self.save_calls += 1
        self._orders[order.id] = order


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def add(
        self, event_id, aggregate_type, aggregate_id, event_type, occurred_at, payload
    ) -> None:  # type: ignore[no-untyped-def]
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


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def save(self, event_type, aggregate_id, payload) -> None:  # type: ignore[no-untyped-def]
        self.events.append(
            {"event_type": event_type, "aggregate_id": aggregate_id, "payload": payload}
        )

    async def get_pending(self, limit=10):  # type: ignore[no-untyped-def]
        return self.events


class FakeIdempotency:
    def __init__(self) -> None:
        self._processed: set[tuple[str, str]] = set()

    async def is_processed(self, eid: str, cname: str) -> bool:
        return (eid, cname) in self._processed

    async def mark_processed(self, eid: str, cname: str) -> None:
        self._processed.add((eid, cname))


def _order(order_id: UUID, status: str) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        id=order_id,
        customer_id="cus_1",
        status=status,
        cancel_reason=None,
        created_at=now,
        updated_at=now,
        items=[OrderItem(product_id="p", quantity=1)],
    )


@pytest.mark.asyncio
async def test_terminal_confirmed_late_reserved_no_ops_skip_recorded() -> None:
    oid = uuid4()
    order_repo = FakeOrderRepository({oid: _order(oid, "confirmed")})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderInventoryResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    await uc.execute(event_id=eid, order_id=oid, result="reserved")
    assert order_repo.save_calls == 0
    assert event_repo.events == []
    assert outbox.events == []
    found = await order_repo.get_by_id(oid)
    assert found is not None and found.status == "confirmed"
    assert await idem.is_processed(eid, "ProcessOrderInventoryResult")
    # duplicate late result no-ops as well
    prev_saves = order_repo.save_calls
    await uc.execute(event_id=eid, order_id=oid, result="reserved")
    assert order_repo.save_calls == prev_saves
    assert event_repo.events == []
    assert outbox.events == []


@pytest.mark.asyncio
async def test_terminal_cancelled_late_rejected_no_ops_skip_recorded() -> None:
    oid = uuid4()
    order_repo = FakeOrderRepository({oid: _order(oid, "cancelled")})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderInventoryResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    await uc.execute(event_id=eid, order_id=oid, result="rejected")
    assert order_repo.save_calls == 0
    assert event_repo.events == []
    assert outbox.events == []
    found = await order_repo.get_by_id(oid)
    assert found is not None and found.status == "cancelled"
    assert await idem.is_processed(eid, "ProcessOrderInventoryResult")


@pytest.mark.asyncio
async def test_terminal_skip_regardless_of_result_value() -> None:
    # confirmed + rejected would raise InvalidStateTransition without guard
    oid = uuid4()
    order_repo = FakeOrderRepository({oid: _order(oid, "confirmed")})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderInventoryResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    await uc.execute(event_id=eid, order_id=oid, result="rejected")
    assert (
        order_repo.save_calls == 0 and event_repo.events == [] and outbox.events == []
    )
    assert await idem.is_processed(eid, "ProcessOrderInventoryResult")
    assert (await order_repo.get_by_id(oid)).status == "confirmed"  # type: ignore[union-attr]
    # cancelled + reserved would also raise without guard
    oid2 = uuid4()
    order_repo2 = FakeOrderRepository({oid2: _order(oid2, "cancelled")})
    event_repo2 = FakeEventRepository()
    outbox2 = FakeOutbox()
    idem2 = FakeIdempotency()
    uc2 = ProcessOrderInventoryResult(order_repo2, event_repo2, outbox2, idem2)  # type: ignore[arg-type]
    eid2 = str(uuid4())
    await uc2.execute(event_id=eid2, order_id=oid2, result="reserved")
    assert (
        order_repo2.save_calls == 0
        and event_repo2.events == []
        and outbox2.events == []
    )
    assert await idem2.is_processed(eid2, "ProcessOrderInventoryResult")


@pytest.mark.asyncio
async def test_pending_reserved_confirms_and_pending_rejected_cancels() -> None:
    # pending -> confirmed on reserved
    oid = uuid4()
    order_repo = FakeOrderRepository({oid: _order(oid, "pending")})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderInventoryResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    await uc.execute(event_id=eid, order_id=oid, result="reserved")
    found = await order_repo.get_by_id(oid)
    assert found is not None and found.status == "confirmed"
    assert order_repo.save_calls == 1
    assert any(e["event_type"] == "InventoryReserved" for e in event_repo.events)
    assert any(e["event_type"] == "OrderConfirmed" for e in outbox.events)
    assert await idem.is_processed(eid, "ProcessOrderInventoryResult")
    # duplicate pending result no second transition
    await uc.execute(event_id=eid, order_id=oid, result="reserved")
    assert order_repo.save_calls == 1
    assert len([e for e in outbox.events if e["event_type"] == "OrderConfirmed"]) == 1
    assert (
        len([e for e in event_repo.events if e["event_type"] == "InventoryReserved"])
        == 1
    )
    # pending -> cancelled on rejected
    oid2 = uuid4()
    order_repo2 = FakeOrderRepository({oid2: _order(oid2, "pending")})
    event_repo2 = FakeEventRepository()
    outbox2 = FakeOutbox()
    idem2 = FakeIdempotency()
    uc2 = ProcessOrderInventoryResult(order_repo2, event_repo2, outbox2, idem2)  # type: ignore[arg-type]
    eid2 = str(uuid4())
    await uc2.execute(event_id=eid2, order_id=oid2, result="rejected")
    found2 = await order_repo2.get_by_id(oid2)
    assert found2 is not None and found2.status == "cancelled"
    assert order_repo2.save_calls == 1
    assert any(e["event_type"] == "InventoryRejected" for e in event_repo2.events)
    assert any(e["event_type"] == "OrderCancelled" for e in outbox2.events)


@pytest.mark.asyncio
async def test_order_not_found_still_raises_and_not_marked() -> None:
    oid = uuid4()
    order_repo = FakeOrderRepository({})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderInventoryResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    with pytest.raises(OrderNotFoundError):
        await uc.execute(event_id=eid, order_id=oid, result="reserved")
    assert not await idem.is_processed(eid, "ProcessOrderInventoryResult")
    assert (
        order_repo.save_calls == 0 and outbox.events == [] and event_repo.events == []
    )
