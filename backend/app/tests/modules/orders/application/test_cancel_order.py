"""Tests for the hardened CancelOrder use case (U4 operator cancel)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.orders.application.cancel_order import CancelOrder
from app.modules.orders.domain.entities import Order
from app.modules.orders.domain.errors import (
    InvalidStateTransitionError,
    OrderNotFoundError,
)
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


def _order(status: str) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        id=uuid4(),
        customer_id="cus_1",
        status=status,
        cancel_reason=None,
        created_at=now,
        updated_at=now,
        items=[],
    )


def _use_case(db_session):  # type: ignore[no-untyped-def]
    return CancelOrder(
        SqlAlchemyOrderRepository(db_session),
        SqlAlchemyEventRepository(db_session),
        SqlAlchemyOutboxRepository(db_session),
    )


async def _timeline(db_session, order_id) -> list:  # type: ignore[no-untyped-def]
    return await SqlAlchemyEventRepository(db_session).get_timeline(
        "order", str(order_id)
    )


async def _outbox(db_session):  # type: ignore[no-untyped-def]
    return await SqlAlchemyOutboxRepository(db_session).get_pending(limit=50)


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancels_from_non_terminal_states_and_emits_once(
        self, db_session
    ) -> None:
        for status in ("pending", "inventory_reserved", "payment_authorized"):
            repo = SqlAlchemyOrderRepository(db_session)
            order = _order(status)
            await repo.save(order)

            use_case = _use_case(db_session)
            returned = await use_case.execute(order.id, "operator_cancelled")

            assert returned.status == "cancelled"
            assert returned.cancel_reason == "operator_cancelled"
            found = await repo.get_by_id(order.id)
            assert found is not None
            assert found.status == "cancelled"
            assert found.cancel_reason == "operator_cancelled"

            timeline = await _timeline(db_session, order.id)
            cancelled_timeline = [
                e for e in timeline if e.event_type == "OrderCancelled"
            ]
            assert len(cancelled_timeline) == 1
            assert cancelled_timeline[0].payload == {
                "status": "cancelled",
                "reason": "operator_cancelled",
            }

            pending = await _outbox(db_session)
            cancelled_outbox = [
                e
                for e in pending
                if e.event_type == "OrderCancelled" and e.aggregate_id == str(order.id)
            ]
            assert len(cancelled_outbox) == 1
            assert cancelled_outbox[0].payload == {
                "status": "cancelled",
                "reason": "operator_cancelled",
            }

    @pytest.mark.asyncio
    async def test_cancel_idempotent_retry_preserves_reason_and_emits_once(
        self, db_session
    ) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = _order("pending")
        await repo.save(order)

        use_case = _use_case(db_session)
        await use_case.execute(order.id, "operator_cancelled")
        returned = await use_case.execute(order.id, "second_reason")

        assert returned.status == "cancelled"
        assert returned.cancel_reason == "operator_cancelled"
        timeline = await _timeline(db_session, order.id)
        assert len([e for e in timeline if e.event_type == "OrderCancelled"]) == 1
        pending = await _outbox(db_session)
        assert (
            len(
                [
                    e
                    for e in pending
                    if e.event_type == "OrderCancelled"
                    and e.aggregate_id == str(order.id)
                ]
            )
            == 1
        )

    @pytest.mark.asyncio
    async def test_cancel_confirmed_order_raises(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = _order("confirmed")
        await repo.save(order)

        use_case = _use_case(db_session)
        with pytest.raises(InvalidStateTransitionError):
            await use_case.execute(order.id, "operator_cancelled")

        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"
        timeline = await _timeline(db_session, order.id)
        assert timeline == []

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_raises(self, db_session) -> None:
        use_case = _use_case(db_session)
        with pytest.raises(OrderNotFoundError):
            await use_case.execute(uuid4(), "operator_cancelled")
