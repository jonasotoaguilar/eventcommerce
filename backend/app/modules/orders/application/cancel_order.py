"""CancelOrder use case (U4 operator cancel).

Operator path owning cancellation from the non-terminal states
``pending``, ``inventory_reserved`` and ``payment_authorized``:

* Missing rows raise ``OrderNotFoundError`` (mapped to 404).
* The entity transition guard remains authoritative: cancelling a
  ``confirmed`` order raises ``InvalidStateTransitionError`` (mapped to
  a stable 409). An already-cancelled order is a state-idempotent no-op
  that preserves the original reason and must not duplicate events.
* The terminal ``OrderCancelled`` timeline + outbox events are emitted
  exactly once per actual transition.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.modules.orders.domain.entities import Order
from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class CancelOrder:
    def __init__(
        self,
        repository: OrderRepository,
        event_repo: SqlAlchemyEventRepository,
        outbox: SqlAlchemyOutboxRepository,
    ) -> None:
        self._repository = repository
        self._event_repo = event_repo
        self._outbox = outbox

    async def execute(self, order_id: UUID, reason: str) -> Order:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")
        # State-idempotent retry: an already-cancelled order keeps its
        # original reason and must not duplicate the terminal events.
        if order.status == "cancelled":
            return order
        order.cancel(reason)
        await self._repository.save(order)
        await self._event_repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id=str(order.id),
            event_type="OrderCancelled",
            occurred_at=datetime.now(timezone.utc),
            payload={"status": "cancelled", "reason": reason},
        )
        await self._outbox.save(
            event_type="OrderCancelled",
            aggregate_id=str(order.id),
            payload={"status": "cancelled", "reason": reason},
        )
        return order
