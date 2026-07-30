"""CreateOrder use case."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.events import OrderCreated
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class CreateOrder:
    def __init__(
        self,
        repository: OrderRepository,
        event_repo: SqlAlchemyEventRepository,
        outbox: SqlAlchemyOutboxRepository,
    ) -> None:
        self._repository = repository
        self._event_repo = event_repo
        self._outbox = outbox

    async def execute(self, customer_id: str, items: list[OrderItem]) -> Order:
        if not items:
            raise ValueError("Order must contain at least one item")

        order = Order(
            id=uuid4(),
            customer_id=customer_id,
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=items,
        )
        await self._repository.save(order)

        event = OrderCreated(
            event_id=uuid4(),
            aggregate_id=order.id,
            occurred_at=datetime.now(timezone.utc),
            customer_id=customer_id,
            items=items,
        )
        await self._event_repo.add(
            event_id=event.event_id,
            aggregate_type="order",
            aggregate_id=str(event.aggregate_id),
            event_type="OrderCreated",
            occurred_at=event.occurred_at,
            payload={"customer_id": customer_id},
        )
        await self._outbox.save(
            event_type="OrderCreated",
            aggregate_id=str(order.id),
            payload={"customer_id": customer_id},
        )
        return order
