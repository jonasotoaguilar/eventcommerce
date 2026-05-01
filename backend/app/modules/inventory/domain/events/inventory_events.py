"""Inventory domain events."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class InventoryReserved:
    event_id: UUID
    order_id: UUID
    product_id: str
    quantity: int
    occurred_at: datetime
