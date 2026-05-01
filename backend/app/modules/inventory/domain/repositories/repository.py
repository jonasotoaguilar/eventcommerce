"""Inventory repository protocol."""

from typing import Protocol

from app.modules.inventory.domain.entities.inventory import Inventory


class InventoryRepository(Protocol):
    async def get_by_product(self, product_id: str) -> Inventory | None: ...
    async def save(self, inventory: Inventory) -> None: ...
