"""Payments dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


class PaymentsContainer(containers.DeclarativeContainer):
    """Payments module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    payment_repo = providers.Factory(SqlAlchemyPaymentRepository, session=session)
    authorize_payment = providers.Factory(AuthorizePayment, repository=payment_repo)
    process_payment_failure = providers.Factory(
        ProcessPaymentFailure, repository=payment_repo
    )


payments_container = PaymentsContainer()
