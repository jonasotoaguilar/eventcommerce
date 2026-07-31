"""Shared domain event base types."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Uses neutral naming (aggregate_id) so it can be shared across
    any bounded context without coupling to a specific aggregate.
    """

    event_id: UUID
    aggregate_id: UUID
    occurred_at: datetime
