"""SQLAlchemy implementation of NotificationRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.repository import NotificationRepository
from app.modules.notifications.infrastructure.models import NotificationModel


class SqlAlchemyNotificationRepository(NotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        result = await self._session.execute(
            select(NotificationModel).where(NotificationModel.id == notification_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    async def save(self, notification: Notification) -> None:
        result = await self._session.execute(
            select(NotificationModel).where(NotificationModel.id == notification.id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.channel = notification.channel
            existing.content = notification.content
            existing.sent_at = notification.sent_at
        else:
            orm = NotificationModel(
                id=notification.id,
                order_id=notification.order_id,
                channel=notification.channel,
                content=notification.content,
                sent_at=notification.sent_at,
            )
            self._session.add(orm)
        await self._session.flush()

    def _to_domain(self, orm: NotificationModel) -> Notification:
        return Notification(
            id=orm.id,
            order_id=orm.order_id,
            channel=orm.channel,
            content=orm.content,
            sent_at=orm.sent_at,
        )
