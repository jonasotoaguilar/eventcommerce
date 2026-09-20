"""Inventory repository protocol."""

from typing import Protocol

from app.modules.inventory.domain.entities import Inventory


class InventoryRepository(Protocol):
    async def get_by_product(self, product_id: str) -> Inventory | None: ...
    async def lock_by_product(self, product_id: str) -> Inventory | None:
        """Return the row locked ``FOR UPDATE`` or ``None`` when missing.

        The lock is held until the session commits or rolls back, so the
        caller can mutate under it without lost updates.
        """
        ...

    async def save(self, inventory: Inventory) -> None: ...
    async def lock_and_check_availability(
        self, items: list[tuple[str, int]]
    ) -> list[Inventory]: ...
