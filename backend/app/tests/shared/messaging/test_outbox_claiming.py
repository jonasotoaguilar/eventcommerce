"""Tests for concurrent outbox claims."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.shared.messaging.models import OutboxEventModel
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


async def _seed_pending_events(session, count: int) -> None:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all(
        [
            OutboxEventModel(
                id=uuid4(),
                event_type="OrderCreated",
                aggregate_id=f"order-{index}",
                payload={"index": index},
                status="pending",
                created_at=created_at + timedelta(seconds=index),
            )
            for index in range(count)
        ]
    )
    await session.commit()


class TestOutboxClaiming:
    @pytest.mark.asyncio
    async def test_get_pending_orders_and_caps_the_batch(self, db_session) -> None:
        await _seed_pending_events(db_session, count=3)

        events = await SqlAlchemyOutboxRepository(db_session).get_pending(limit=2)

        assert [event.aggregate_id for event in events] == ["order-0", "order-1"]

    @pytest.mark.asyncio
    async def test_concurrent_workers_claim_disjoint_rows(self, engine) -> None:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as seed_session:
            await _seed_pending_events(seed_session, count=4)

        async with (
            session_factory() as first_session,
            session_factory() as second_session,
        ):
            first = await SqlAlchemyOutboxRepository(first_session).get_pending(limit=2)
            second = await SqlAlchemyOutboxRepository(second_session).get_pending(
                limit=2
            )

            first_ids = {event.id for event in first}
            second_ids = {event.id for event in second}
            assert first_ids.isdisjoint(second_ids)
            assert len(first_ids | second_ids) == 4

            await first_session.commit()
            await second_session.commit()
