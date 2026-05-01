"""Order domain events."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class OrderCreated:
    event_id: UUID
    order_id: UUID
    customer_id: str
    occurred_at: datetime
