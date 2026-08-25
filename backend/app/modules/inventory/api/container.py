"""Inventory dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.application.order_status import OrderStatusQuery
from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class InventoryContainer(containers.DeclarativeContainer):
    """Inventory module container."""

    session = providers.Dependency(instance_of=AsyncSession)

    order_status_query = providers.Dependency(instance_of=OrderStatusQuery)

    inventory_repo = providers.Factory(SqlAlchemyInventoryRepository, session=session)
    outbox_repo = providers.Factory(SqlAlchemyOutboxRepository, session=session)
    idempotency = providers.Factory(ProcessedEventStore, session=session)

    process_inventory_reservation = providers.Factory(
        ProcessInventoryReservation,
        inventory_repo=inventory_repo,
        outbox=outbox_repo,
        idempotency=idempotency,
        order_status=order_status_query,
    )


inventory_container = InventoryContainer()
