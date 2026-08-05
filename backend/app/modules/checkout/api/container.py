"""Checkout dependency injection container (design: request-local session).

The container exposes a request-local ``session`` dependency: routes
override it with the request's ``AsyncSession`` before resolving use
cases, so every repository and use case shares one transaction per
request — atomically coordinating commerce, outbox, and idempotency.
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.application.checkout import Checkout
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class CheckoutContainer(containers.DeclarativeContainer):
    """Checkout module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    order_repo = providers.Factory(SqlAlchemyOrderRepository, session=session)
    event_repo = providers.Factory(SqlAlchemyEventRepository, session=session)
    outbox_repo = providers.Factory(SqlAlchemyOutboxRepository, session=session)
    inventory_repo = providers.Factory(SqlAlchemyInventoryRepository, session=session)
    payment_repo = providers.Factory(SqlAlchemyPaymentRepository, session=session)
    notification_repo = providers.Factory(
        SqlAlchemyNotificationRepository, session=session
    )
    idempotency = providers.Factory(ProcessedEventStore, session=session)

    create_order = providers.Factory(
        CreateOrder,
        repository=order_repo,
        event_repo=event_repo,
        outbox=outbox_repo,
    )
    authorize_payment = providers.Factory(AuthorizePayment, repository=payment_repo)
    process_payment_failure = providers.Factory(
        ProcessPaymentFailure, repository=payment_repo
    )
    notifier = providers.Factory(SendOrderNotification, repository=notification_repo)

    checkout = providers.Factory(
        Checkout,
        session=session,
        order_repo=order_repo,
        create_order=create_order,
        inventory_repo=inventory_repo,
        outbox=outbox_repo,
        idempotency=idempotency,
        authorize_payment=authorize_payment,
        process_payment_failure=process_payment_failure,
        notifier=notifier,
    )


checkout_container = CheckoutContainer()
