"""Tests for SendOrderNotification use case."""

from uuid import uuid4

import pytest

from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.domain.errors import ChannelNotSupportedError
from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.repository import NotificationRepository


class InMemoryNotificationRepository(NotificationRepository):
    def __init__(self) -> None:
        self.notifications: list[Notification] = []

    async def get_by_id(self, notification_id):
        for n in self.notifications:
            if n.id == notification_id:
                return n
        return None

    async def save(self, notification: Notification) -> None:
        self.notifications.append(notification)


class TestSendOrderNotification:
    @pytest.mark.asyncio
    async def test_sends_notification(self) -> None:
        repo = InMemoryNotificationRepository()
        use_case = SendOrderNotification(repo)
        notification = await use_case.execute(
            order_id=uuid4(), channel="email", content="Your order is confirmed"
        )

        assert notification.channel == "email"
        assert notification.content == "Your order is confirmed"
        assert len(repo.notifications) == 1

    @pytest.mark.asyncio
    async def test_unsupported_channel_raises(self) -> None:
        repo = InMemoryNotificationRepository()
        use_case = SendOrderNotification(repo)
        with pytest.raises(ChannelNotSupportedError, match="not supported"):
            await use_case.execute(order_id=uuid4(), channel="fax", content="hello")
