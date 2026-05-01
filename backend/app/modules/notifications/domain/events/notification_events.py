"""Notification domain events."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class OrderNotificationSent:
    event_id: UUID
    order_id: UUID
    channel: str
    occurred_at: datetime

