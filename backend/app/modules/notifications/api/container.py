"""Notifications dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.process_order_notification import (
    ProcessOrderNotification,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from app.shared.messaging.idempotency import ProcessedEventStore


class NotificationsContainer(containers.DeclarativeContainer):
    """Notifications module container."""

    session = providers.Dependency(instance_of=AsyncSession)

    notification_repo = providers.Factory(
        SqlAlchemyNotificationRepository, session=session
    )
    idempotency = providers.Factory(ProcessedEventStore, session=session)
    notifier = providers.Factory(SendOrderNotification, repository=notification_repo)
    process_order_notification = providers.Factory(
        ProcessOrderNotification,
        notifier=notifier,
        idempotency=idempotency,
    )


notifications_container = NotificationsContainer()
