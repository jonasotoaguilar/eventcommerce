"""ProcessOrderInventoryResult use case."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.shared.events.repository import EventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class ProcessOrderInventoryResult:
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
        if await self._idempotency.is_processed(
            event_id, "ProcessOrderInventoryResult"
        ):
            return
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")

        if result == "reserved":
            order.confirm()
            await self._order_repo.save(order)
            await self._event_repo.add(
                event_id=uuid4(),
                aggregate_type="order",
                aggregate_id=str(order.id),
                event_type="InventoryReserved",
                occurred_at=datetime.now(timezone.utc),
                payload={"result": "reserved"},
            )
            await self._outbox.save(
                event_type="OrderConfirmed",
                aggregate_id=str(order.id),
                payload={"status": "confirmed"},
            )
        elif result == "rejected":
            order.cancel(reason="insufficient_stock")
            await self._order_repo.save(order)
            await self._event_repo.add(
                event_id=uuid4(),
                aggregate_type="order",
                aggregate_id=str(order.id),
                event_type="InventoryRejected",
                occurred_at=datetime.now(timezone.utc),
                payload={"result": "rejected", "reason": "insufficient_stock"},
            )
            await self._outbox.save(
                event_type="OrderCancelled",
                aggregate_id=str(order.id),
                payload={"status": "cancelled", "reason": "insufficient_stock"},
            )
        await self._idempotency.mark_processed(event_id, "ProcessOrderInventoryResult")
