"""Tests for the extended ProcessedEventStore claim/cache API.

Slice 1 tasks 1.3/1.4 (RED): failing tests that pin the advisory-lock claim
lifecycle (NEW/REPLAY_MATCH/CONFLICT), the durable replay cache, the 16 KiB
response cap, and the rollback-safe in-progress lifecycle against a real
Postgres database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.messaging.idempotency import (
    CachedResponse,
    ClaimResult,
    ProcessedEventStore,
    ResponseTooLargeError,
)

CONSUMER = "Checkout"
KEY = "idem-key-0001"
H1 = "a" * 64
H2 = "b" * 64
BODY = {"order_id": "ord-0001", "status": "confirmed"}


class _Rollback(Exception):
    """Raised inside a transaction to force a rollback."""


@pytest_asyncio.fixture
async def session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


async def _complete(session: AsyncSession, key: str, body: dict) -> None:
    store = ProcessedEventStore(session)
    assert await store.claim(key, CONSUMER, H1) == ClaimResult.NEW
    await store.complete_with_response(key, CONSUMER, 201, body, H1)


async def _stored_hash(session: AsyncSession, key: str) -> str:
    row = (
        await session.execute(
            text(
                "SELECT payload_hash FROM processed_events "
                "WHERE event_id = :k AND consumer_name = :c"
            ),
            {"k": key, "c": CONSUMER},
        )
    ).one()
    return row.payload_hash


class TestReplayCache:
    @pytest.mark.asyncio
    async def test_replay_returns_cached_status_and_body(self, session_factory) -> None:
        s1, s2 = session_factory(), session_factory()
        async with s1.begin():
            await _complete(s1, KEY, BODY)

        async with s2.begin():
            store2 = ProcessedEventStore(s2)
            assert await store2.claim(KEY, CONSUMER, H1) == ClaimResult.REPLAY_MATCH
            cached = await store2.fetch_cached(KEY, CONSUMER)
        assert cached == CachedResponse(status=201, body=BODY)

    @pytest.mark.asyncio
    async def test_conflict_does_not_mutate_first_execution(
        self, session_factory
    ) -> None:
        s1, s2 = session_factory(), session_factory()
        async with s1.begin():
            await _complete(s1, KEY, BODY)

        async with s2.begin():
            store2 = ProcessedEventStore(s2)
            assert await store2.claim(KEY, CONSUMER, H2) == ClaimResult.CONFLICT
            cached = await store2.fetch_cached(KEY, CONSUMER)
            assert cached == CachedResponse(status=201, body=BODY)
            assert await _stored_hash(s2, KEY) == H1

    @pytest.mark.asyncio
    async def test_fetch_cached_returns_none_when_row_missing(
        self, session_factory
    ) -> None:
        s = session_factory()
        async with s.begin():
            assert await ProcessedEventStore(s).fetch_cached(KEY, CONSUMER) is None


class TestConcurrentRaces:
    async def _race(
        self,
        session_factory,
        second_hash: str,
        body: dict,
    ) -> tuple[ClaimResult, CachedResponse | None, str]:
        """Tx1 claims+completes while tx2 races the same key.

        Returns (second claim result, cached response seen by tx2, stored
        payload hash) after both transactions settle.
        """
        s1 = session_factory()
        store1 = ProcessedEventStore(s1)
        async with s1.begin():
            assert await store1.claim(KEY, CONSUMER, H1) == ClaimResult.NEW

            s2 = session_factory()
            started = asyncio.Event()

            async def second_claim() -> ClaimResult:
                started.set()
                async with s2.begin():
                    return await ProcessedEventStore(s2).claim(
                        KEY, CONSUMER, second_hash
                    )

            task = asyncio.create_task(second_claim())
            await started.wait()
            # Tx2 must block on the advisory xact lock held by tx1.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            await store1.complete_with_response(KEY, CONSUMER, 201, body, H1)

        second_result = await task
        async with s2.begin():
            cached = await ProcessedEventStore(s2).fetch_cached(KEY, CONSUMER)
            stored_hash = await _stored_hash(s2, KEY)
        return second_result, cached, stored_hash

    @pytest.mark.asyncio
    async def test_concurrent_identical_payloads_execute_once(
        self, session_factory
    ) -> None:
        second_result, cached, _ = await self._race(session_factory, H1, BODY)
        assert second_result == ClaimResult.REPLAY_MATCH
        assert cached == CachedResponse(status=201, body=BODY)

    @pytest.mark.asyncio
    async def test_concurrent_differing_payload_conflicts_without_mutation(
        self, session_factory
    ) -> None:
        second_result, cached, stored_hash = await self._race(session_factory, H2, BODY)
        assert second_result == ClaimResult.CONFLICT
        assert cached == CachedResponse(status=201, body=BODY)
        assert stored_hash == H1


class TestClaimLifecycle:
    @pytest.mark.asyncio
    async def test_claim_new_inserts_in_progress_row(self, session_factory) -> None:
        s = session_factory()
        async with s.begin():
            store = ProcessedEventStore(s)
            assert await store.claim(KEY, CONSUMER, H1) == ClaimResult.NEW
            assert await store.fetch_cached(KEY, CONSUMER) is None

    @pytest.mark.asyncio
    async def test_rollback_removes_uncommitted_claim(self, session_factory) -> None:
        s1, s2 = session_factory(), session_factory()
        with pytest.raises(_Rollback):
            async with s1.begin():
                assert (
                    await ProcessedEventStore(s1).claim(KEY, CONSUMER, H1)
                    == ClaimResult.NEW
                )
                raise _Rollback()

        async with s2.begin():
            store2 = ProcessedEventStore(s2)
            assert await store2.claim(KEY, CONSUMER, H1) == ClaimResult.NEW
            assert await store2.fetch_cached(KEY, CONSUMER) is None

    @pytest.mark.asyncio
    async def test_release_claim_removes_in_progress_row(self, session_factory) -> None:
        s1, s2 = session_factory(), session_factory()
        async with s1.begin():
            store1 = ProcessedEventStore(s1)
            assert await store1.claim(KEY, CONSUMER, H1) == ClaimResult.NEW
            await store1.release_claim(KEY, CONSUMER)
            assert await store1.claim(KEY, CONSUMER, H1) == ClaimResult.NEW

        async with s2.begin():
            assert await ProcessedEventStore(s2).fetch_cached(KEY, CONSUMER) is None

    @pytest.mark.asyncio
    async def test_release_claim_does_not_remove_completed_row(
        self, session_factory
    ) -> None:
        s1, s2 = session_factory(), session_factory()
        async with s1.begin():
            await _complete(s1, KEY, BODY)

        async with s2.begin():
            store2 = ProcessedEventStore(s2)
            await store2.release_claim(KEY, CONSUMER)
            cached = await store2.fetch_cached(KEY, CONSUMER)
        assert cached == CachedResponse(status=201, body=BODY)

    @pytest.mark.asyncio
    async def test_claim_reclaims_legacy_processed_row(self, session_factory) -> None:
        s1, s2 = session_factory(), session_factory()
        async with s1.begin():
            await ProcessedEventStore(s1).mark_processed(KEY, CONSUMER)

        async with s2.begin():
            store2 = ProcessedEventStore(s2)
            assert await store2.claim(KEY, CONSUMER, H1) == ClaimResult.NEW
            assert await store2.fetch_cached(KEY, CONSUMER) is None

    @pytest.mark.asyncio
    async def test_legacy_mark_and_is_processed_still_work(
        self, session_factory
    ) -> None:
        s = session_factory()
        async with s.begin():
            store = ProcessedEventStore(s)
            await store.mark_processed(KEY, "inventory_consumer")
            assert await store.is_processed(KEY, "inventory_consumer") is True
            assert await store.is_processed(KEY, CONSUMER) is False


class TestResponseCap:
    @pytest.mark.asyncio
    async def test_complete_rejects_body_over_16kib(self, session_factory) -> None:
        s = session_factory()
        store = ProcessedEventStore(s)
        async with s.begin():
            assert await store.claim(KEY, CONSUMER, H1) == ClaimResult.NEW
            with pytest.raises(ResponseTooLargeError):
                await store.complete_with_response(
                    KEY, CONSUMER, 201, {"blob": "x" * 17000}, H1
                )
            assert await store.fetch_cached(KEY, CONSUMER) is None

    @pytest.mark.asyncio
    async def test_complete_accepts_body_under_cap(self, session_factory) -> None:
        s = session_factory()
        body = {"blob": "y" * 16000}
        async with s.begin():
            await _complete(s, KEY, body)
            cached = await ProcessedEventStore(s).fetch_cached(KEY, CONSUMER)
        assert cached == CachedResponse(status=201, body=body)
