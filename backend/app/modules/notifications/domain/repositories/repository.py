"""Notification repository protocol."""

from typing import Protocol
from uuid import UUID

from app.modules.notifications.domain.entities.notification import Notification


class NotificationRepository(Protocol):
    async def get_by_id(self, notification_id: UUID) -> Notification | None: ...
    async def save(self, notification: Notification) -> None: ...
