"""Payment domain entities."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass
class Payment:
    id: UUID
    order_id: UUID
    status: str
    amount: Decimal
    currency: str
    created_at: datetime
    failure_reason: str | None = None


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str
