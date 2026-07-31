"""ProcessInventoryReservation use case."""

from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.repository import InventoryRepository
from app.modules.inventory.domain.services import reserve_stock
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository
from app.shared.messaging.idempotency import ProcessedEventStore


class ProcessInventoryReservation:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        outbox: SqlAlchemyOutboxRepository,
        idempotency: ProcessedEventStore,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._outbox = outbox
        self._idempotency = idempotency

    async def execute(self, event_id: str, order_id: str, items: list[dict]) -> None:
        if await self._idempotency.is_processed(
            event_id, "ProcessInventoryReservation"
        ):
            return
        try:
            for item in items:
                product_id = item["product_id"]
                quantity = item["quantity"]
                inventory = await self._inventory_repo.get_by_product(product_id)
                if inventory is None:
                    raise InsufficientStockError(f"Product {product_id} not found")
                reserve_stock(inventory, quantity)
                await self._inventory_repo.save(inventory)
            await self._outbox.save(
                event_type="InventoryReserved",
                aggregate_id=order_id,
                payload={"items": items},
            )
        except InsufficientStockError:
            await self._outbox.save(
                event_type="InventoryRejected",
                aggregate_id=order_id,
                payload={"items": items, "reason": "insufficient_stock"},
            )
        await self._idempotency.mark_processed(event_id, "ProcessInventoryReservation")
