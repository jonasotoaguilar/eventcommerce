"""SQLAlchemy implementation of NotificationRepository."""

from uuid import UUID

from app.modules.notifications.domain.entities.notification import Notification
from app.modules.notifications.domain.repositories.repository import (
    NotificationRepository,
)


class SqlAlchemyNotificationRepository(NotificationRepository):
    def __init__(self, session: object) -> None:
        self._session = session

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        return None

    async def save(self, notification: Notification) -> None:
        pass
