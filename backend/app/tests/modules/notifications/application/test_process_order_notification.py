"""Unit tests for ProcessOrderNotification (task 3.3) — STRICT TDD."""

from uuid import uuid4

import pytest

from app.modules.notifications.application.process_order_notification import (
    ProcessOrderNotification,
)


class FakeNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[object, str, str]] = []
        self._fail = fail

    async def execute(self, order_id, channel, content):  # type: ignore[no-untyped-def]
        if self._fail:
            raise RuntimeError("channel down")
        self.calls.append((order_id, channel, content))
        # mimic Notification return
        return None


class FakeIdempotency:
    def __init__(self) -> None:
        self._processed: set[tuple[str, str]] = set()
        self.mark_calls: list[tuple[str, str]] = []

    async def is_processed(self, eid: str, cname: str) -> bool:
        return (eid, cname) in self._processed

    async def mark_processed(self, eid: str, cname: str) -> None:
        self.mark_calls.append((eid, cname))
        self._processed.add((eid, cname))


@pytest.mark.asyncio
async def test_confirmed_notifies_once_and_marks_processed() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderConfirmed", aggregate_id=str(oid)
    )
    assert len(notifier.calls) == 1
    order_id, channel, content = notifier.calls[0]
    assert str(order_id) == str(oid)
    assert channel == "email"
    assert content == "Your order has been confirmed"
    assert await idem.is_processed(eid, "ProcessOrderNotification")
    assert idem.mark_calls == [(eid, "ProcessOrderNotification")]


@pytest.mark.asyncio
async def test_cancelled_notifies_with_cancelled_content() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderCancelled", aggregate_id=str(oid)
    )
    assert len(notifier.calls) == 1
    _, channel, content = notifier.calls[0]
    assert channel == "email"
    assert content == "Your order could not be completed"
    assert await idem.is_processed(eid, "ProcessOrderNotification")


@pytest.mark.asyncio
async def test_duplicate_notifies_once_no_second_mark() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderConfirmed", aggregate_id=str(oid)
    )
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderConfirmed", aggregate_id=str(oid)
    )
    assert len(notifier.calls) == 1
    assert len(idem.mark_calls) == 1


@pytest.mark.asyncio
async def test_duplicate_skips_without_revalidating() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderConfirmed", aggregate_id=str(oid)
    )
    # duplicate with different type and malformed id must still no-op, not raise
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderCreated", aggregate_id="order-123"
    )
    await handler.execute(
        payload={}, event_id=eid, event_type="OrderCancelled", aggregate_id="not-a-uuid"
    )
    assert len(notifier.calls) == 1
    assert len(idem.mark_calls) == 1


@pytest.mark.asyncio
async def test_notification_failure_not_marked() -> None:
    notifier = FakeNotifier(fail=True)
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    with pytest.raises(RuntimeError, match="channel down"):
        await handler.execute(
            payload={}, event_id=eid, event_type="OrderConfirmed", aggregate_id=str(oid)
        )
    assert not await idem.is_processed(eid, "ProcessOrderNotification")
    assert idem.mark_calls == []
    assert len(notifier.calls) == 0


@pytest.mark.asyncio
async def test_malformed_uuid_raises_no_notification_no_mark() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    eid = str(uuid4())
    with pytest.raises(ValueError):
        await handler.execute(
            payload={},
            event_id=eid,
            event_type="OrderConfirmed",
            aggregate_id="order-123",
        )
    assert len(notifier.calls) == 0
    assert not await idem.is_processed(eid, "ProcessOrderNotification")


@pytest.mark.asyncio
async def test_unknown_event_type_raises_no_notification_no_mark() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    handler = ProcessOrderNotification(notifier, idem)  # type: ignore[arg-type]
    oid = uuid4()
    eid = str(uuid4())
    with pytest.raises(ValueError, match="unsupported"):
        await handler.execute(
            payload={}, event_id=eid, event_type="OrderCreated", aggregate_id=str(oid)
        )
    assert len(notifier.calls) == 0
    assert not await idem.is_processed(eid, "ProcessOrderNotification")


@pytest.mark.asyncio
async def test_mandatory_dependencies_required() -> None:
    notifier = FakeNotifier()
    idem = FakeIdempotency()
    with pytest.raises(TypeError):
        ProcessOrderNotification(notifier)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ProcessOrderNotification(idempotency=idem)  # type: ignore[call-arg]
