"""Payment domain entity."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Payment:
    id: UUID
    order_id: UUID
    status: str
    amount: float
    currency: str
    created_at: datetime

