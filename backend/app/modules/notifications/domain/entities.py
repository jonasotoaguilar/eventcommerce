"""Notification domain entities."""

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


@dataclass(frozen=True)
class NotificationChannel:
    name: str
