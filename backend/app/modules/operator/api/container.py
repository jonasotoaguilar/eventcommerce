"""Operator dependency injection container (request-local session).

Every repository shares the container's single request session, so each
operator read composes its contexts in one transaction without adding a
dependency between those modules.
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.operator.application.list_catalog_with_stock import (
    ListCatalogWithStock,
)
from app.modules.operator.application.list_order_queue import ListOrderQueue
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
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
    product_repo = providers.Factory(SqlAlchemyProductRepository, session=session)
    inventory_repo = providers.Factory(SqlAlchemyInventoryRepository, session=session)

    list_order_queue = providers.Factory(
        ListOrderQueue,
        order_repository=order_repo,
        payment_repository=payment_repo,
    )

    list_catalog_with_stock = providers.Factory(
        ListCatalogWithStock,
        product_repository=product_repo,
        inventory_repository=inventory_repo,
    )


operator_container = OperatorContainer()
