"""ConfirmOrder use case (U4 operator confirm).

Operator path owning the ``payment_authorized -> confirmed`` transition:

* Only an order staged in ``payment_authorized`` may confirm. An
  already-confirmed order is a state-idempotent no-op (no re-emit). Any
  other state — including ``pending``, whose synchronous
  ``pending -> confirmed`` shortcut stays owned by ``Checkout`` calling
  ``Order.confirm`` directly, and ``cancelled`` — raises
  ``InvalidStateTransitionError`` (mapped to a stable 409 at the API
  boundary). The entity guard remains the final authority after the
  operator policy check.
* Missing rows raise ``OrderNotFoundError`` (mapped to 404).
* The terminal ``OrderConfirmed`` timeline + outbox events are emitted
  exactly once per actual transition.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.modules.orders.domain.entities import Order
from app.modules.orders.domain.errors import (
    InvalidStateTransitionError,
    OrderNotFoundError,
)
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class ConfirmOrder:
    def __init__(
        self,
        repository: OrderRepository,
        event_repo: SqlAlchemyEventRepository,
        outbox: SqlAlchemyOutboxRepository,
    ) -> None:
        self._repository = repository
        self._event_repo = event_repo
        self._outbox = outbox

    async def execute(self, order_id: UUID) -> Order:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")
        # State-idempotent retry: an already-confirmed order is done and
        # must not duplicate the terminal events.
        if order.status == "confirmed":
            return order
        # Operator policy: only a staged payment_authorized order may
        # confirm through this path.
        if order.status != "payment_authorized":
            raise InvalidStateTransitionError(
                f"Cannot confirm order in status {order.status}"
            )
        order.confirm()
        await self._repository.save(order)
        await self._event_repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id=str(order.id),
            event_type="OrderConfirmed",
            occurred_at=datetime.now(timezone.utc),
            payload={"status": "confirmed"},
        )
        await self._outbox.save(
            event_type="OrderConfirmed",
            aggregate_id=str(order.id),
            payload={"status": "confirmed"},
        )
        return order
