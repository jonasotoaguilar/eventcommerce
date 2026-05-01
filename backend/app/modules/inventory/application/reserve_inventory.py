"""ReserveInventory use case."""
from uuid import UUID

from app.modules.inventory.domain.entities.inventory import Inventory
from app.modules.inventory.domain.errors.domain_errors import InsufficientStockError
from app.modules.inventory.domain.repositories.repository import InventoryRepository
from app.modules.inventory.domain.services.inventory_domain_service import reserve_stock


class ReserveInventory:
    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID, product_id: str, quantity: int) -> None:
        inventory = await self._repository.get_by_product(product_id)
        if inventory is None:
            raise InsufficientStockError(f"Product {product_id} not found")
        reserve_stock(inventory, quantity)
        await self._repository.save(inventory)

