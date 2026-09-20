"""ProcessOrderPaymentResult use case (U3 expand-order-state-machine).

Orders-owned consumer for the payment result events ``PaymentAuthorized``
and ``PaymentRejected``. It owns the ``inventory_reserved`` order
transitions:

* ``PaymentAuthorized`` requires the order to be staged in
  ``inventory_reserved``, moves it to ``payment_authorized``, and emits
  the order-owned internal ``OrderPaymentAuthorized`` event that stages
  confirmation. Any other state is stale or conflicting: terminal orders
  are done, an already-authorized order is a state-idempotent no-op, and
  any other non-terminal state (e.g. a still-pending order) means this
  event is out of order — claim it without emitting rather than racing
  another transition.
* ``PaymentRejected`` cancels an ``inventory_reserved`` order with the
  existing ``payment_declined`` reason and emits terminal
  ``OrderCancelled``. Terminal orders are done; any other non-terminal
  state is stale/conflicting and is claimed without side effects so a
  late or duplicate rejection can never move a confirmed, pending, or
  already-authorized order.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.repository import EventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

CONSUMER_NAME = "ProcessOrderPaymentResult"

CANCEL_REASON_PAYMENT_DECLINED = "payment_declined"

_TERMINAL_ORDER_STATUSES = ("confirmed", "cancelled")


class ProcessOrderPaymentResult:
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

    async def execute(self, event_id: str, order_id: UUID, result: str) -> None:
        if await self._idempotency.is_processed(event_id, CONSUMER_NAME):
            return
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")

        if order.status in _TERMINAL_ORDER_STATUSES:
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        if result == "authorized":
            # Only a staged order may advance. An already-authorized order
            # is a state-idempotent redelivery: claim without re-emitting.
            # Any other non-terminal state is out of order: claim silently.
            if order.status == "payment_authorized":
                await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
                return
            if order.status != "inventory_reserved":
                await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
                return
            order.authorize_payment()
            await self._order_repo.save(order)
            await self._event_repo.add(
                event_id=uuid4(),
                aggregate_type="order",
                aggregate_id=str(order.id),
                event_type="PaymentAuthorized",
                occurred_at=datetime.now(timezone.utc),
                payload={"result": "authorized"},
            )
            await self._outbox.save(
                event_type="OrderPaymentAuthorized",
                aggregate_id=str(order.id),
                payload={"status": "payment_authorized"},
            )
        elif result == "rejected":
            # Only a staged order may cancel on payment rejection. Any other
            # non-terminal state (pending, payment_authorized) is a stale or
            # conflicting delivery: claim without mutating.
            if order.status != "inventory_reserved":
                await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
                return
            order.cancel(reason=CANCEL_REASON_PAYMENT_DECLINED)
            await self._order_repo.save(order)
            await self._event_repo.add(
                event_id=uuid4(),
                aggregate_type="order",
                aggregate_id=str(order.id),
                event_type="PaymentRejected",
                occurred_at=datetime.now(timezone.utc),
                payload={
                    "result": "rejected",
                    "reason": CANCEL_REASON_PAYMENT_DECLINED,
                },
            )
            await self._outbox.save(
                event_type="OrderCancelled",
                aggregate_id=str(order.id),
                payload={
                    "status": "cancelled",
                    "reason": CANCEL_REASON_PAYMENT_DECLINED,
                },
            )
        await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
