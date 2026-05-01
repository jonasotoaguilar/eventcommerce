"""Payment domain events."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class PaymentAuthorized:
    event_id: UUID
    order_id: UUID
    payment_id: UUID
    occurred_at: datetime

