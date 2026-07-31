"""Notifications dependency injection container."""

from dependency_injector import containers


class NotificationsContainer(containers.DeclarativeContainer):
    """Notifications module container."""


notifications_container = NotificationsContainer()
