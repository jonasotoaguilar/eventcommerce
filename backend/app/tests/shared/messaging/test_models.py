"""Tests for messaging ORM models."""

from app.shared.messaging.models import OutboxEventModel, ProcessedEventModel


class TestMessagingModels:
    def test_outbox_events_columns(self) -> None:
        cols = {c.name for c in OutboxEventModel.__table__.columns}
        assert "id" in cols
        assert "event_type" in cols
        assert "aggregate_id" in cols
        assert "payload" in cols
        assert "status" in cols
        assert "created_at" in cols
        assert "published_at" in cols

    def test_processed_events_columns(self) -> None:
        cols = {c.name for c in ProcessedEventModel.__table__.columns}
        assert "event_id" in cols
        assert "consumer_name" in cols
        assert "processed_at" in cols
