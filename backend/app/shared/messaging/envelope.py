"""Event envelope model."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: UUID
    event_type: Literal[
        "OrderCreated",
        "InventoryReserved",
        "InventoryRejected",
        "OrderConfirmed",
        "OrderCancelled",
    ]
    aggregate_id: UUID
    correlation_id: UUID
    causation_id: UUID | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    version: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        aggregate_id: UUID,
        correlation_id: UUID,
        payload: dict[str, Any],
        causation_id: UUID | None = None,
    ) -> "EventEnvelope":
        return cls(
            event_id=uuid4(),
            event_type=event_type,  # type: ignore[arg-type]
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload,
        )
