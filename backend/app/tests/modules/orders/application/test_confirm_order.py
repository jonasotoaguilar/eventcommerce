"""Tests for the hardened ConfirmOrder use case (U4 operator confirm)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.orders.application.confirm_order import ConfirmOrder
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
    return ConfirmOrder(
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


class TestConfirmOrder:
    @pytest.mark.asyncio
    async def test_confirms_payment_authorized_and_emits_once(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = _order("payment_authorized")
        await repo.save(order)

        use_case = _use_case(db_session)
        returned = await use_case.execute(order.id)

        assert returned.status == "confirmed"
        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"

        timeline = await _timeline(db_session, order.id)
        confirmed_timeline = [e for e in timeline if e.event_type == "OrderConfirmed"]
        assert len(confirmed_timeline) == 1
        assert confirmed_timeline[0].payload == {"status": "confirmed"}

        pending = await _outbox(db_session)
        confirmed_outbox = [e for e in pending if e.event_type == "OrderConfirmed"]
        assert len(confirmed_outbox) == 1
        assert confirmed_outbox[0].aggregate_id == str(order.id)
        assert confirmed_outbox[0].payload == {"status": "confirmed"}

    @pytest.mark.asyncio
    async def test_confirm_idempotent_retry_emits_once(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = _order("payment_authorized")
        await repo.save(order)

        use_case = _use_case(db_session)
        await use_case.execute(order.id)
        returned = await use_case.execute(order.id)

        assert returned.status == "confirmed"
        timeline = await _timeline(db_session, order.id)
        assert len([e for e in timeline if e.event_type == "OrderConfirmed"]) == 1
        pending = await _outbox(db_session)
        assert len([e for e in pending if e.event_type == "OrderConfirmed"]) == 1

    @pytest.mark.asyncio
    async def test_confirm_invalid_statuses_raise(self, db_session) -> None:
        for status in ("pending", "inventory_reserved", "cancelled"):
            repo = SqlAlchemyOrderRepository(db_session)
            order = _order(status)
            if status == "cancelled":
                order.cancel_reason = "operator_cancelled"
            await repo.save(order)

            use_case = _use_case(db_session)
            with pytest.raises(InvalidStateTransitionError):
                await use_case.execute(order.id)

            found = await repo.get_by_id(order.id)
            assert found is not None
            assert found.status == status
            timeline = await _timeline(db_session, order.id)
            assert timeline == []
            pending = await _outbox(db_session)
            assert [e for e in pending if e.aggregate_id == str(order.id)] == []

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_order_raises(self, db_session) -> None:
        use_case = _use_case(db_session)

        with pytest.raises(OrderNotFoundError):
            await use_case.execute(uuid4())
