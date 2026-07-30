"""Tests for notifications ORM models."""

from app.modules.notifications.infrastructure.models import NotificationModel


class TestNotificationModel:
    def test_notification_columns(self) -> None:
        cols = {c.name for c in NotificationModel.__table__.columns}
        assert "id" in cols
        assert "order_id" in cols
        assert "channel" in cols
        assert "content" in cols
        assert "sent_at" in cols
