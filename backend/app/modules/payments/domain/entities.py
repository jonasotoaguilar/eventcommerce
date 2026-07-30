"""Payment domain entities."""

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


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str
