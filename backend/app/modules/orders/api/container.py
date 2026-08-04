"""Orders dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.application.cancel_order import CancelOrder
from app.modules.orders.application.confirm_order import ConfirmOrder
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.application.get_order import GetOrder
from app.modules.orders.application.get_order_timeline import GetOrderTimeline
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class OrdersContainer(containers.DeclarativeContainer):
    """Orders module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    order_repo = providers.Factory(SqlAlchemyOrderRepository, session=session)
    event_repo = providers.Factory(SqlAlchemyEventRepository, session=session)
    outbox_repo = providers.Factory(SqlAlchemyOutboxRepository, session=session)
    idempotency = providers.Factory(ProcessedEventStore, session=session)

    create_order = providers.Factory(
        CreateOrder,
        repository=order_repo,
        event_repo=event_repo,
        outbox=outbox_repo,
    )
    get_order = providers.Factory(GetOrder, repository=order_repo)
    get_order_timeline = providers.Factory(GetOrderTimeline, event_repo=event_repo)
    confirm_order = providers.Factory(ConfirmOrder, repository=order_repo)
    cancel_order = providers.Factory(CancelOrder, repository=order_repo)
    process_order_inventory_result = providers.Factory(
        ProcessOrderInventoryResult,
        order_repo=order_repo,
        event_repo=event_repo,
        outbox=outbox_repo,
        idempotency=idempotency,
    )


orders_container = OrdersContainer()
