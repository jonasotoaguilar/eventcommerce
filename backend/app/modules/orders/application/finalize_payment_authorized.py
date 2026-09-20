"""FinalizePaymentAuthorized use case (U3 expand-order-state-machine).

Orders-owned finalizer for the internal ``OrderPaymentAuthorized`` event.
It owns the ``payment_authorized -> confirmed`` transition and emits
terminal ``OrderConfirmed`` exactly once:

* Only an order staged in ``payment_authorized`` may confirm. An
  already-confirmed order is a state-idempotent no-op; a cancelled order
  is terminal and a conflicting finalizer is claimed without side
  effects; any other non-terminal state (pending, inventory_reserved) is
  out of order and is claimed without emitting rather than racing
  another transition.
* Notifications stay driven by the terminal ``OrderConfirmed`` event, so
  this use case never notifies directly.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.repository import EventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

CONSUMER_NAME = "FinalizePaymentAuthorized"


class FinalizePaymentAuthorized:
    def __init__(
        self,
        order_repo: OrderRepository,
        event_repo: EventRepository,
        outbox: SqlAlchemyOutboxRepository,
        idempotency: ProcessedEventStore,
    ) -> None:
        self._order_repo = order_repo
        self._event_repo = event_repo
        self._outbox = outbox
        self._idempotency = idempotency

    async def execute(self, event_id: str, order_id: UUID) -> None:
        if await self._idempotency.is_processed(event_id, CONSUMER_NAME):
            return
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")

        # Terminal and out-of-order guards: only payment_authorized advances.
        # Confirmed restages and cancelled/conflicting finals are claimed
        # without duplicating the terminal event.
        if order.status == "confirmed":
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return
        if order.status == "cancelled":
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return
        if order.status != "payment_authorized":
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        order.confirm()
        await self._order_repo.save(order)
        await self._event_repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id=str(order.id),
            event_type="OrderPaymentAuthorized",
            occurred_at=datetime.now(timezone.utc),
            payload={"status": "payment_authorized"},
        )
        await self._outbox.save(
            event_type="OrderConfirmed",
            aggregate_id=str(order.id),
            payload={"status": "confirmed"},
        )
        await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
