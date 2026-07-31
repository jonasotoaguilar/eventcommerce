"""Integration tests for outbox repository."""

import pytest

from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class TestSqlAlchemyOutboxRepository:
    @pytest.mark.asyncio
    async def test_save_event(self, db_session) -> None:
        repo = SqlAlchemyOutboxRepository(db_session)
        await repo.save(
            event_type="OrderCreated",
            aggregate_id="order-123",
            payload={"customer_id": "cus_1"},
        )

        events = await repo.get_pending(limit=10)
        assert len(events) == 1
        assert events[0].event_type == "OrderCreated"
        assert events[0].aggregate_id == "order-123"
        assert events[0].payload == {"customer_id": "cus_1"}
        assert events[0].status == "pending"

    @pytest.mark.asyncio
    async def test_mark_published(self, db_session) -> None:
        repo = SqlAlchemyOutboxRepository(db_session)
        await repo.save(
            event_type="OrderCreated",
            aggregate_id="order-123",
            payload={},
        )
        events = await repo.get_pending(limit=10)
        event_id = events[0].id
        await repo.mark_published(event_id)

        events = await repo.get_pending(limit=10)
        assert len(events) == 0
