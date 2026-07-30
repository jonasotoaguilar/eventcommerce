"""Notifications dependency injection container."""

from dependency_injector import containers


class NotificationsContainer(containers.DeclarativeContainer):
    """Notifications module container."""

    wiring_config = containers.WiringConfiguration(
        modules=["app.modules.notifications.api.routes"]
    )


notifications_container = NotificationsContainer()
