import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from app.messaging_runtime import MessagingRuntime, _jittered_backoff


@pytest.mark.asyncio
async def _fast_sleep(_: float) -> None:
    await asyncio.sleep(0.005)


class TestBrokerDownHealthy:
    @pytest.mark.asyncio
    async def test_start_returns_when_broker_down(self, caplog):
        pub = AsyncMock()
        pub.connect = AsyncMock(side_effect=Exception("down"))
        pub.close = AsyncMock()
        con = AsyncMock()
        con.connect = AsyncMock(side_effect=Exception("down"))
        con.close = AsyncMock()
        con.start = AsyncMock()
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(
            pub, con, worker, 0.05, 10, sleep=_fast_sleep, jitter=lambda lo, hi: 0.005
        )
        with caplog.at_level(logging.WARNING, logger="app.messaging_runtime"):
            await asyncio.wait_for(rt.start(), timeout=0.5)
            await asyncio.sleep(0.02)
            assert pub.connect.await_count >= 1
            assert "connect_retry" in caplog.text
        await asyncio.wait_for(rt.stop(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_retry_recovers_after_one_failure(self):
        pub = AsyncMock()
        pub.connect = AsyncMock(side_effect=[Exception("down"), None])
        pub.close = AsyncMock()
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(
            pub, None, worker, 0.05, 5, sleep=_fast_sleep, jitter=lambda lo, hi: 0.005
        )
        await rt.start()
        await asyncio.sleep(0.02)
        assert pub.connect.await_count >= 2
        await rt.stop()


class TestBackoff:
    def test_capped_at_30(self):
        assert _jittered_backoff(0, base=1.0, cap=30.0, jitter=lambda lo, hi: hi) == 1.0
        assert _jittered_backoff(3, base=1.0, cap=30.0, jitter=lambda lo, hi: hi) == 8.0
        assert (
            _jittered_backoff(5, base=1.0, cap=30.0, jitter=lambda lo, hi: hi) == 30.0
        )
        assert (
            _jittered_backoff(10, base=1.0, cap=30.0, jitter=lambda lo, hi: hi) == 30.0
        )
        assert _jittered_backoff(3, base=1.0, cap=30.0, jitter=lambda lo, hi: lo) == 0.0
        assert _jittered_backoff(1, base=2.0, cap=30.0, jitter=lambda lo, hi: hi) == 4.0

    def test_full_jitter_range(self):
        assert (
            _jittered_backoff(
                2, base=1.0, cap=30.0, jitter=lambda lo, hi: (lo + hi) / 2
            )
            == 2.0
        )
        assert _jittered_backoff(
            2, base=1.0, cap=30.0, jitter=lambda lo, hi: hi
        ) != _jittered_backoff(2, base=1.0, cap=30.0, jitter=lambda lo, hi: lo)


class TestScheduler:
    @pytest.mark.asyncio
    async def test_uses_poll_and_batch(self):
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(None, None, worker, 0.02, 7)
        await rt.start()
        await asyncio.sleep(0.07)
        await rt.stop()
        assert worker.run_once.await_count >= 2
        for c in worker.run_once.await_args_list:
            assert c.kwargs.get("batch_size") == 7

    @pytest.mark.asyncio
    async def test_different_batch_honored(self):
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(None, None, worker, 0.02, 3)
        await rt.start()
        await asyncio.sleep(0.05)
        await rt.stop()
        for c in worker.run_once.await_args_list:
            assert c.kwargs.get("batch_size") == 3


class TestShutdown:
    @pytest.mark.asyncio
    async def test_closes_within_10s(self):
        pub = AsyncMock()
        pub.close = AsyncMock()
        con = AsyncMock()
        con.close = AsyncMock()
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(pub, con, worker, 0.1, 10)
        await rt.start()
        await asyncio.sleep(0.02)
        start = asyncio.get_event_loop().time()
        await asyncio.wait_for(rt.stop(), timeout=10.0)
        assert asyncio.get_event_loop().time() - start < 10.0
        pub.close.assert_awaited_once()
        con.close.assert_awaited_once()
        assert rt._scheduler_task is None or rt._scheduler_task.done()

    @pytest.mark.asyncio
    async def test_shutdown_without_deps(self):
        worker = AsyncMock()
        worker.run_once = AsyncMock(return_value=0)
        rt = MessagingRuntime(None, None, worker, 0.05, 5)
        await rt.start()
        await asyncio.sleep(0.02)
        await asyncio.wait_for(rt.stop(), timeout=2.0)
        assert rt._scheduler_task is None or rt._scheduler_task.done()
