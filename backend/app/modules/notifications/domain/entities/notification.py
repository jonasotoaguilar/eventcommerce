"""Notification domain entity."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Notification:
    id: UUID
    order_id: UUID
    channel: str
    content: str
    sent_at: datetime

