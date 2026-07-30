"""Tests for notification domain models."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.notifications.domain.entities import Notification, NotificationChannel


class TestNotification:
    def test_notification_attributes(self) -> None:
        now = datetime.now(timezone.utc)
        n = Notification(
            id=uuid4(),
            order_id=uuid4(),
            channel="sms",
            content="Shipped",
            sent_at=now,
        )
        assert n.channel == "sms"
        assert n.content == "Shipped"


class TestNotificationChannel:
    def test_channel_value_object(self) -> None:
        ch = NotificationChannel(name="push")
        assert ch.name == "push"
