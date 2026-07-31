"""Tests for processed event idempotency."""

from uuid import uuid4

import pytest

from app.shared.messaging.idempotency import ProcessedEventStore


class TestProcessedEventStore:
    @pytest.mark.asyncio
    async def test_mark_and_is_processed(self, db_session) -> None:
        store = ProcessedEventStore(db_session)
        event_id = str(uuid4())
        await store.mark_processed(event_id, "inventory_consumer")

        assert await store.is_processed(event_id, "inventory_consumer") is True
        assert await store.is_processed(event_id, "orders_consumer") is False
        assert await store.is_processed(str(uuid4()), "inventory_consumer") is False

    @pytest.mark.asyncio
    async def test_mark_duplicate_raises(self, db_session) -> None:
        store = ProcessedEventStore(db_session)
        event_id = str(uuid4())
        await store.mark_processed(event_id, "inventory_consumer")
        # Duplicate should be silently ignored or raise; we choose ignore
        await store.mark_processed(event_id, "inventory_consumer")
        assert await store.is_processed(event_id, "inventory_consumer") is True
