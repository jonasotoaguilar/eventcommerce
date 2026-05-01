"""SendOrderNotification use case."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.modules.notifications.domain.entities.notification import Notification
from app.modules.notifications.domain.errors.domain_errors import ChannelNotSupportedError
from app.modules.notifications.domain.repositories.repository import NotificationRepository
from app.modules.notifications.domain.services.notification_domain_service import is_channel_supported


class SendOrderNotification:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID, channel: str, content: str) -> Notification:
        if not is_channel_supported(channel):
            raise ChannelNotSupportedError(f"Channel {channel} not supported")
        notification = Notification(
            id=uuid4(),
            order_id=order_id,
            channel=channel,
            content=content,
            sent_at=datetime.now(timezone.utc),
        )
        await self._repository.save(notification)
        return notification

