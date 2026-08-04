"""Shared messaging SQLAlchemy ORM models."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Integer, CHAR, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ProcessedEventModel(Base):
    """Durable idempotency record for one (key, consumer) pair.

    For checkout, ``event_id`` is the ``Idempotency-Key`` header and the row
    additionally caches the response payload so a replay returns the exact
    original status code and body without re-executing the side effects.

    ``state`` transitions:
    * ``in_progress``  – a request has claimed the row; another concurrent
      request under the same key must wait on the advisory transaction lock
      and then observe either the cached response or a mismatch.
    * ``completed``   – the response is durably stored.  Replays return
      the cached status and body.  ``payload_hash``, ``response_status``,
      and ``response_body`` are required (DB-level check constraint).
    * ``processed``    – legacy/simple idempotency: side effects were
      applied once and no response is cached.

    The composite primary key remains ``(event_id, consumer_name)``.
    """

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    consumer_name: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="processed")
