"""Tests for outbox worker."""

from unittest.mock import AsyncMock

import pytest

from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository
from app.shared.messaging.outbox_worker import OutboxWorker


class TestOutboxWorker:
    @pytest.mark.asyncio
    async def test_processes_pending_events(self, db_session) -> None:
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        publisher = AsyncMock()
        worker = OutboxWorker(outbox_repo, publisher)

        await outbox_repo.save(
            event_type="OrderCreated",
            aggregate_id="order-123",
            payload={"customer_id": "cus_1"},
        )

        processed = await worker.run_once()
        assert processed == 1
        assert publisher.publish.call_count == 1

    @pytest.mark.asyncio
    async def test_no_pending_events(self, db_session) -> None:
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        publisher = AsyncMock()
        worker = OutboxWorker(outbox_repo, publisher)

        processed = await worker.run_once()
        assert processed == 0
        assert publisher.publish.call_count == 0
