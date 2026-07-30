"""Payments dependency injection container."""

from dependency_injector import containers


class PaymentsContainer(containers.DeclarativeContainer):
    """Payments module container."""

    wiring_config = containers.WiringConfiguration(
        modules=["app.modules.payments.api.routes"]
    )


payments_container = PaymentsContainer()
