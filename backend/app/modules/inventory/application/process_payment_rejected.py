"""ProcessPaymentRejected compensation (U3 expand-order-state-machine).

Inventory-side consumer for ``PaymentRejected``. It loads the order's own
lines and releases the previously reserved quantities back to available
stock exactly once per message:

* Idempotency is claimed under a dedicated inventory consumer name, so a
  duplicate delivery never double-releases even when the orders-side
  payment-result consumer shares the same message.
* Strict stale/terminal guard: only an order in ``inventory_reserved``
  proves the reservation happened, so only that state releases.
  ``pending``, ``payment_authorized``, ``confirmed``, and ``cancelled``
  are claimed without mutating inventory, so a stale or conflicting
  rejection can never inflate stock or double-release after the
  orders-side transition. The shared-queue runtime therefore runs this
  compensation before the orders-side cancellation while the order is
  still staged.
* This use case never mutates order status and never emits order events:
  order transitions stay owned by the orders context.
"""

from uuid import UUID

from app.modules.inventory.domain.repository import InventoryRepository
from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.shared.messaging.idempotency import ProcessedEventStore

CONSUMER_NAME = "ProcessPaymentRejected"


class ProcessPaymentRejected:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        order_repo: OrderRepository,
        idempotency: ProcessedEventStore,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._order_repo = order_repo
        self._idempotency = idempotency

    async def execute(self, event_id: str, order_id: UUID) -> None:
        if await self._idempotency.is_processed(event_id, CONSUMER_NAME):
            return
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")

        # Strict guard: only inventory_reserved proves the reservation
        # happened for this order. Every other status is stale or
        # terminal (pending: out of order; payment_authorized/confirmed:
        # conflicting success; cancelled: already transitioned), so claim
        # it without touching inventory.
        if order.status != "inventory_reserved":
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        for item in getattr(order, "items", []):
            product_id = getattr(item, "product_id", None)
            quantity = getattr(item, "quantity", None)
            if not isinstance(product_id, str) or not product_id:
                continue
            if not isinstance(quantity, int) or quantity <= 0:
                continue
            inventory = await self._inventory_repo.get_by_product(product_id)
            if inventory is None:
                continue
            inventory.reserved_quantity -= quantity
            inventory.available_quantity += quantity
            await self._inventory_repo.save(inventory)

        await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
