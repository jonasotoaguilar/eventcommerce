"""Idempotency store using processed_events table."""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.messaging.models import ProcessedEventModel

MAX_RESPONSE_BODY_BYTES = 16 * 1024  # 16 KiB durable replay-cache cap


class ClaimResult(Enum):
    """Outcome of acquiring an idempotency claim for one (key, consumer)."""

    NEW = "new"
    REPLAY_MATCH = "replay_match"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class CachedResponse:
    status: int
    body: dict[str, Any]


class ResponseTooLargeError(Exception):
    """The response body exceeds the durable replay-cache cap."""


async def acquire_claim_lock(
    session: AsyncSession, consumer_name: str, key: str
) -> None:
    """Serialize claimers of one (consumer, key) across processes.

    Uses a transaction-scoped advisory lock (``pg_advisory_xact_lock``), so
    the lock is released when the enclosing transaction commits or rolls
    back. The lock name for checkout is exactly ``Checkout:<key>``.
    """
    lock_name = f"{consumer_name}:{key}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_name, 0))"),
        {"lock_name": lock_name},
    )


def _response_bytes(body: dict[str, Any]) -> int:
    return len(json.dumps(body, separators=(",", ":")).encode("utf-8"))


class ProcessedEventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_processed(self, event_id: str, consumer_name: str) -> bool:
        return await self._get_row(event_id, consumer_name) is not None

    async def mark_processed(self, event_id: str, consumer_name: str) -> None:
        if await self.is_processed(event_id, consumer_name):
            return
        orm = ProcessedEventModel(
            event_id=event_id,
            consumer_name=consumer_name,
        )
        self._session.add(orm)
        await self._session.flush()

    async def claim(
        self, key: str, consumer_name: str, payload_hash: str
    ) -> ClaimResult:
        """Acquire the idempotency claim for ``(key, consumer_name)``.

        Must run inside the request's transaction. Returns:
        * ``NEW`` — the key is free; an ``in_progress`` row was created and
          the caller must execute and finish with ``complete_with_response``
          (or roll back to abandon the claim).
        * ``REPLAY_MATCH`` — a completed row exists with the same payload
          hash; the caller returns the cached response without executing.
        * ``CONFLICT`` — a completed row exists with a different payload
          hash; the caller answers ``409`` and executes nothing.
        """
        await acquire_claim_lock(self._session, consumer_name, key)
        row = await self._get_row(key, consumer_name)
        if row is None:
            self._session.add(
                ProcessedEventModel(
                    event_id=key,
                    consumer_name=consumer_name,
                    payload_hash=payload_hash,
                    state="in_progress",
                )
            )
            await self._session.flush()
            return ClaimResult.NEW
        if row.state == "completed":
            if row.payload_hash == payload_hash:
                return ClaimResult.REPLAY_MATCH
            return ClaimResult.CONFLICT
        # A stale in_progress or legacy processed row: we hold the key lock,
        # so the previous holder is gone — reclaim the row as NEW.
        row.state = "in_progress"
        row.payload_hash = payload_hash
        await self._session.flush()
        return ClaimResult.NEW

    async def complete_with_response(
        self,
        key: str,
        consumer_name: str,
        status: int,
        body: dict[str, Any],
        payload_hash: str,
    ) -> None:
        """Persist the terminal response and mark the claim ``completed``."""
        if _response_bytes(body) > MAX_RESPONSE_BODY_BYTES:
            raise ResponseTooLargeError(
                f"response body exceeds {MAX_RESPONSE_BODY_BYTES} bytes"
            )
        row = await self._get_row(key, consumer_name)
        if row is None:
            row = ProcessedEventModel(event_id=key, consumer_name=consumer_name)
            self._session.add(row)
        row.state = "completed"
        row.payload_hash = payload_hash
        row.response_status = status
        row.response_body = body
        await self._session.flush()

    async def release_claim(self, key: str, consumer_name: str) -> None:
        """Abandon an in-progress claim; completed rows are never removed."""
        row = await self._get_row(key, consumer_name)
        if row is not None and row.state == "in_progress":
            await self._session.delete(row)
            await self._session.flush()

    async def fetch_cached(self, key: str, consumer_name: str) -> CachedResponse | None:
        """Return the durable cached response for a completed claim, if any."""
        row = await self._get_row(key, consumer_name)
        if (
            row is None
            or row.state != "completed"
            or row.response_status is None
            or row.response_body is None
        ):
            return None
        return CachedResponse(status=row.response_status, body=row.response_body)

    async def _get_row(
        self, event_id: str, consumer_name: str
    ) -> ProcessedEventModel | None:
        result = await self._session.execute(
            select(ProcessedEventModel).where(
                ProcessedEventModel.event_id == event_id,
                ProcessedEventModel.consumer_name == consumer_name,
            )
        )
        return result.scalar_one_or_none()
