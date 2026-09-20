"""Tests for ProcessOrderPaymentResult (U3 payment-result transitions)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.orders.application.process_payment_result import (
    CONSUMER_NAME,
    ProcessOrderPaymentResult,
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
        items=[OrderItem(product_id="p1", quantity=2)],
    )


def _harness(order: Order | None):  # type: ignore[no-untyped-def]
    order_repo = FakeOrderRepository({order.id: order} if order else {})
    event_repo = FakeEventRepository()
    outbox = FakeOutbox()
    idem = FakeIdempotency()
    uc = ProcessOrderPaymentResult(order_repo, event_repo, outbox, idem)  # type: ignore[arg-type]
    return uc, order_repo, event_repo, outbox, idem


class TestAuthorizedPath:
    @pytest.mark.asyncio
    async def test_authorized_advances_to_payment_authorized(self) -> None:
        oid = uuid4()
        uc, order_repo, event_repo, outbox, idem = _harness(
            _order(oid, "inventory_reserved")
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid, result="authorized")

        found = await order_repo.get_by_id(oid)
        assert found is not None and found.status == "payment_authorized"
        assert order_repo.save_calls == 1
        assert any(e["event_type"] == "PaymentAuthorized" for e in event_repo.events)
        staged = [
            e for e in outbox.events if e["event_type"] == "OrderPaymentAuthorized"
        ]
        assert len(staged) == 1
        assert staged[0]["payload"] == {"status": "payment_authorized"}
        assert staged[0]["aggregate_id"] == str(oid)
        assert not any(e["event_type"] == "OrderConfirmed" for e in outbox.events)
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_authorized_restage_is_state_idempotent(self) -> None:
        oid = uuid4()
        uc, order_repo, event_repo, outbox, idem = _harness(
            _order(oid, "inventory_reserved")
        )
        await uc.execute(event_id=str(uuid4()), order_id=oid, result="authorized")
        await uc.execute(event_id=str(uuid4()), order_id=oid, result="authorized")
        assert order_repo.save_calls == 1
        assert (
            len(
                [
                    e
                    for e in outbox.events
                    if e["event_type"] == "OrderPaymentAuthorized"
                ]
            )
            == 1
        )
        assert (
            len(
                [e for e in event_repo.events if e["event_type"] == "PaymentAuthorized"]
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_authorized_duplicate_event_id_emits_once(self) -> None:
        oid = uuid4()
        uc, order_repo, event_repo, outbox, _ = _harness(
            _order(oid, "inventory_reserved")
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid, result="authorized")
        await uc.execute(event_id=eid, order_id=oid, result="authorized")
        assert order_repo.save_calls == 1
        assert len(outbox.events) == 1


class TestRejectedPath:
    @pytest.mark.asyncio
    async def test_rejected_cancels_with_payment_declined(self) -> None:
        oid = uuid4()
        uc, order_repo, event_repo, outbox, idem = _harness(
            _order(oid, "inventory_reserved")
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid, result="rejected")

        found = await order_repo.get_by_id(oid)
        assert found is not None and found.status == "cancelled"
        assert found.cancel_reason == "payment_declined"
        assert any(e["event_type"] == "PaymentRejected" for e in event_repo.events)
        terminal = [e for e in outbox.events if e["event_type"] == "OrderCancelled"]
        assert len(terminal) == 1
        assert terminal[0]["payload"] == {
            "status": "cancelled",
            "reason": "payment_declined",
        }
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_rejected_duplicate_emits_once(self) -> None:
        oid = uuid4()
        uc, order_repo, _, outbox, _ = _harness(_order(oid, "inventory_reserved"))
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid, result="rejected")
        await uc.execute(event_id=eid, order_id=oid, result="rejected")
        assert order_repo.save_calls == 1
        assert (
            len([e for e in outbox.events if e["event_type"] == "OrderCancelled"]) == 1
        )


class TestGuards:
    @pytest.mark.asyncio
    async def test_terminal_orders_are_skipped_and_claimed(self) -> None:
        for status in ("confirmed", "cancelled"):
            for result in ("authorized", "rejected"):
                oid = uuid4()
                uc, order_repo, event_repo, outbox, idem = _harness(_order(oid, status))
                eid = str(uuid4())
                await uc.execute(event_id=eid, order_id=oid, result=result)
                assert order_repo.save_calls == 0
                assert event_repo.events == []
                assert outbox.events == []
                assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_stale_pending_is_ignored(self) -> None:
        for result in ("authorized", "rejected"):
            oid = uuid4()
            uc, order_repo, event_repo, outbox, idem = _harness(_order(oid, "pending"))
            eid = str(uuid4())
            await uc.execute(event_id=eid, order_id=oid, result=result)
            found = await order_repo.get_by_id(oid)
            assert found is not None and found.status == "pending"
            assert order_repo.save_calls == 0
            assert outbox.events == []
            assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_conflicting_payment_authorized_ignores_rejection(self) -> None:
        oid = uuid4()
        uc, order_repo, _, outbox, idem = _harness(_order(oid, "payment_authorized"))
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid, result="rejected")
        found = await order_repo.get_by_id(oid)
        assert found is not None and found.status == "payment_authorized"
        assert order_repo.save_calls == 0
        assert outbox.events == []
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_missing_order_raises_and_not_marked(self) -> None:
        uc, _, _, outbox, idem = _harness(None)
        oid, eid = uuid4(), str(uuid4())
        with pytest.raises(OrderNotFoundError):
            await uc.execute(event_id=eid, order_id=oid, result="authorized")
        assert not await idem.is_processed(eid, CONSUMER_NAME)
        assert outbox.events == []
