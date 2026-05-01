"""Order domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Order:
    id: UUID
    customer_id: str
    status: str
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
