"""Operator dependency injection container (request-local session).

Both repositories share the container's single request session, so the
queue read composes the orders and payments contexts in one
transaction without adding a dependency between those modules.
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.operator.application.list_order_queue import ListOrderQueue
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


class OperatorContainer(containers.DeclarativeContainer):
    """Operator module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    order_repo = providers.Factory(SqlAlchemyOrderRepository, session=session)
    payment_repo = providers.Factory(SqlAlchemyPaymentRepository, session=session)

    list_order_queue = providers.Factory(
        ListOrderQueue,
        order_repository=order_repo,
        payment_repository=payment_repo,
    )


operator_container = OperatorContainer()
