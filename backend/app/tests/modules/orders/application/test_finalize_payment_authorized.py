"""Tests for FinalizePaymentAuthorized (U3 confirmation finalizer)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.orders.application.finalize_payment_authorized import (
    CONSUMER_NAME,
    FinalizePaymentAuthorized,
)
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.errors import OrderNotFoundError


class FakeOrderRepository:
    def __init__(self, orders: dict[UUID, Order]) -> None:
        self._orders = dict(orders)
        self.save_calls = 0

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

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
        items=[OrderItem(product_id="p1", quantity=1)],
    )


def _harness(order: Order | None):  # type: ignore[no-untyped-def]
    order_repo = FakeOrderRepository({order.id: order} if order else {})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = FinalizePaymentAuthorized(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    return uc, order_repo, event_repo, outbox, idem


class TestFinalizePaymentAuthorized:
    @pytest.mark.asyncio
    async def test_confirms_and_emits_exactly_once(self) -> None:
        oid = uuid4()
        uc, order_repo, _, outbox, idem = _harness(_order(oid, "payment_authorized"))
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)

        found = await order_repo.get_by_id(oid)
        assert found is not None and found.status == "confirmed"
        terminal = [e for e in outbox.events if e["event_type"] == "OrderConfirmed"]
        assert len(terminal) == 1
        assert terminal[0]["payload"] == {"status": "confirmed"}
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_duplicate_event_id_emits_once(self) -> None:
        oid = uuid4()
        uc, order_repo, _, outbox, _ = _harness(_order(oid, "payment_authorized"))
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)
        await uc.execute(event_id=eid, order_id=oid)
        assert order_repo.save_calls == 1
        assert (
            len([e for e in outbox.events if e["event_type"] == "OrderConfirmed"]) == 1
        )

    @pytest.mark.asyncio
    async def test_restage_with_new_event_id_is_state_idempotent(self) -> None:
        oid = uuid4()
        uc, order_repo, _, outbox, _ = _harness(_order(oid, "payment_authorized"))
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert order_repo.save_calls == 1
        assert (
            len([e for e in outbox.events if e["event_type"] == "OrderConfirmed"]) == 1
        )

    @pytest.mark.asyncio
    async def test_terminal_cancelled_is_claimed_without_confirm(self) -> None:
        oid = uuid4()
        uc, order_repo, event_repo, outbox, idem = _harness(_order(oid, "cancelled"))
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)
        assert order_repo.save_calls == 0
        assert outbox.events == []
        assert event_repo.events == []
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_stale_non_authorized_states_are_ignored(self) -> None:
        for status in ("pending", "inventory_reserved"):
            oid = uuid4()
            uc, order_repo, _, outbox, idem = _harness(_order(oid, status))
            eid = str(uuid4())
            await uc.execute(event_id=eid, order_id=oid)
            found = await order_repo.get_by_id(oid)
            assert found is not None and found.status == status
            assert order_repo.save_calls == 0
            assert outbox.events == []
            assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_missing_order_raises_and_not_marked(self) -> None:
        uc, _, _, outbox, idem = _harness(None)
        oid, eid = uuid4(), str(uuid4())
        with pytest.raises(OrderNotFoundError):
            await uc.execute(event_id=eid, order_id=oid)
        assert not await idem.is_processed(eid, CONSUMER_NAME)
        assert outbox.events == []
