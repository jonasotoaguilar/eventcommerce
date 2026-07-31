"""Minimal event store protocol and read-model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class TimelineEvent:
    event_id: UUID
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class EventRepository(Protocol):
    async def add(
        self,
        event_id: UUID,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> None: ...

    async def get_timeline(
        self, aggregate_type: str, aggregate_id: str
    ) -> list[TimelineEvent]: ...
