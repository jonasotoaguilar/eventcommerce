"""Payments dependency injection container."""

from dependency_injector import containers


class PaymentsContainer(containers.DeclarativeContainer):
    """Payments module container."""


payments_container = PaymentsContainer()
