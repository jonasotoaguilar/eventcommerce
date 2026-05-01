"""ReleaseInventory use case."""

from app.modules.inventory.domain.repositories.repository import InventoryRepository


class ReleaseInventory:
    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository

    async def execute(self, product_id: str, quantity: int) -> None:
        inventory = await self._repository.get_by_product(product_id)
        if inventory is not None:
            inventory.reserved_quantity -= quantity
            inventory.available_quantity += quantity
            await self._repository.save(inventory)
