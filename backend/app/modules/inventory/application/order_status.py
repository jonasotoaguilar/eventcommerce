"""Inventory-owned order status query seam."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class OrderStatusQuery(Protocol):
    """Inventory-owned port to read order status without importing orders internals."""

    async def get_status(self, order_id: UUID) -> str | None: ...
