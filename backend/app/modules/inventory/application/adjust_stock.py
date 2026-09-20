"""AdjustStock use case (U1 catalog-cart).

Operator-only at the API boundary. Applies a signed delta to
``available_quantity``; negative deltas that would drive stock below zero
raise :class:`InsufficientStockError`. Missing inventory rows raise
:class:`InventoryNotFoundError` — rows are seeded at zero by product
creation, so a missing row means the product was never provisioned
through the catalog boundary.

The row is locked ``FOR UPDATE`` before mutation so concurrent
adjustments serialize instead of losing updates.
"""

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.errors import InventoryNotFoundError
from app.modules.inventory.domain.repository import InventoryRepository
from app.modules.inventory.domain.services import adjust_available_stock


class AdjustStock:
    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository

    async def execute(self, product_id: str, delta: int) -> Inventory:
        inventory = await self._repository.lock_by_product(product_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Product {product_id} not found")
        adjust_available_stock(inventory, delta)
        await self._repository.save(inventory)
        return inventory
