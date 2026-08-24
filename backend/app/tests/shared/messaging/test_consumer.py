import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.messaging.consumer import ConsumerBinding, MessageConsumer


def _hf(h=None):
    hm = h or AsyncMock()
    return MagicMock(return_value=hm), hm


def _msg(body=b'{"k":"v"}', mid=None, et="OrderCreated", aid="agg-1", headers=None):
    m = AsyncMock()
    m.body = body
    m.message_id = mid or str(uuid4())
    m.headers = (
        headers
        if headers is not None
        else {
            k: v
            for k, v in [("event_type", et), ("aggregate_id", aid)]
            if v is not None
        }
    )
    m.ack = AsyncMock()
    m.nack = AsyncMock()
    return m


def _sf():
    sess = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=None)
    sess.begin = MagicMock(return_value=ctx)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=sess)
    cm.__aexit__ = AsyncMock(return_value=None)
    f = MagicMock(return_value=cm)
    f._mock_session = sess
    return f


async def _connect(c):
    with patch("app.shared.messaging.consumer.aio_pika.connect_robust") as mc:
        conn = AsyncMock()
        ch = AsyncMock()
        ex = AsyncMock()
        q = AsyncMock()
        conn.channel.return_value = ch
        ch.declare_exchange.return_value = ex
        ch.declare_queue.return_value = q
        mc.return_value = conn
        await c.connect()
        return conn, ch, ex, q, mc


class TestRegistry:
    def test_dup(self):
        f1, _ = _hf()
        f2, _ = _hf()
        with pytest.raises(ValueError, match="duplicate queue"):
            MessageConsumer(
                "amqp://x/",
                [
                    ConsumerBinding("q1", ("OrderCreated",), "c1", f1),
                    ConsumerBinding("q1", ("InventoryReserved",), "c2", f2),
                ],
                _sf(),
            )
        with pytest.raises(ValueError, match="duplicate event_type"):
            MessageConsumer(
                "amqp://x/",
                [
                    ConsumerBinding("q1", ("OrderCreated",), "c1", f1),
                    ConsumerBinding("q2", ("OrderCreated",), "c2", f2),
                ],
                _sf(),
            )


class TestTopology:
    @pytest.mark.asyncio
    async def test_durable(self):
        f1, _ = _hf()
        f2, _ = _hf()
        f3, _ = _hf()
        bs = [
            ConsumerBinding("inventory.order_created", ("OrderCreated",), "inv", f1),
            ConsumerBinding(
                "orders.inventory_result",
                ("InventoryReserved", "InventoryRejected"),
                "ord",
                f2,
            ),
            ConsumerBinding(
                "notifications.order_terminal",
                ("OrderConfirmed", "OrderCancelled"),
                "notif",
                f3,
            ),
        ]
        with patch("app.shared.messaging.consumer.aio_pika.connect_robust") as mc:
            conn = AsyncMock()
            ch = AsyncMock()
            ex = AsyncMock()
            q1 = AsyncMock()
            q2 = AsyncMock()
            q3 = AsyncMock()
            conn.channel.return_value = ch
            ch.declare_exchange.return_value = ex
            ch.declare_queue.side_effect = lambda n, durable=False, **kw: {
                "inventory.order_created": q1,
                "orders.inventory_result": q2,
                "notifications.order_terminal": q3,
            }[n]
            mc.return_value = conn
            c = MessageConsumer("amqp://x/", bs, _sf())
            await c.connect()
            mc.assert_awaited_once_with("amqp://x/")
            ch.declare_exchange.assert_awaited_once()
            _, kw = ch.declare_exchange.await_args
            assert kw.get("durable") is True
            import aio_pika

            a, kw = ch.declare_exchange.await_args
            assert (
                kw.get("type") == aio_pika.ExchangeType.TOPIC
                or a[1] == aio_pika.ExchangeType.TOPIC
            )
            assert ch.declare_queue.await_count == 3
            for call in ch.declare_queue.await_args_list:
                assert call.kwargs.get("durable") is True
            ch.set_qos.assert_awaited_once_with(prefetch_count=1)
            assert q1.bind.await_count == 1
            q1.bind.assert_awaited_with(ex, routing_key="OrderCreated")
            assert q2.bind.await_count == 2
            assert {c.kwargs["routing_key"] for c in q2.bind.await_args_list} == {
                "InventoryReserved",
                "InventoryRejected",
            }
            assert q3.bind.await_count == 2
            assert {c.kwargs["routing_key"] for c in q3.bind.await_args_list} == {
                "OrderConfirmed",
                "OrderCancelled",
            }
            # also verify start registers consume with no_ack False on one queue
            await c.start()
            for q in [q1, q2, q3]:
                assert q.consume.await_count == 1
                _, kw = q.consume.await_args
                assert kw.get("no_ack") is False


class TestDispatch:
    @pytest.mark.asyncio
    async def test_invalid_acked(self, caplog):
        f, _ = _hf()
        c = MessageConsumer(
            "amqp://x/",
            [ConsumerBinding("inventory.order_created", ("OrderCreated",), "inv", f)],
            _sf(),
        )
        await _connect(c)
        m1 = _msg(et="Unknown", aid="a1")
        with caplog.at_level(logging.WARNING, logger="app.shared.messaging.consumer"):
            await c._handle_message(m1)
        m1.ack.assert_awaited_once()
        m2 = _msg(et="OrderCreated", aid="a1")
        m2.message_id = None
        with caplog.at_level(logging.WARNING, logger="app.shared.messaging.consumer"):
            await c._handle_message(m2)
        m2.ack.assert_awaited_once()
        m3 = _msg(body=b"not-json", et="OrderCreated", aid="a1")
        with caplog.at_level(logging.WARNING, logger="app.shared.messaging.consumer"):
            await c._handle_message(m3)
        m3.ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success(self, caplog):
        factory, handler = _hf()
        sf = _sf()
        c = MessageConsumer(
            "amqp://x/",
            [
                ConsumerBinding(
                    "inventory.order_created", ("OrderCreated",), "inv", factory
                )
            ],
            sf,
        )
        await _connect(c)
        m = _msg(
            body=json.dumps({"customer_id": "cus_secret_123"}).encode(),
            et="OrderCreated",
            aid="agg-123",
            mid="evt-123",
        )
        with caplog.at_level(logging.INFO, logger="app.shared.messaging.consumer"):
            await c._handle_message(m)
        m.ack.assert_awaited_once()
        m.nack.assert_not_awaited()
        factory.assert_called_once()
        handler.assert_awaited_once()
        assert "cus_secret_123" not in caplog.text
        args = handler.await_args
        assert args and args.kwargs.get("payload") == {"customer_id": "cus_secret_123"}
        assert factory.call_args[0][0] is sf._mock_session

    @pytest.mark.asyncio
    async def test_failure(self, caplog):
        factory, handler = _hf()
        handler.side_effect = RuntimeError("boom")
        c = MessageConsumer(
            "amqp://x/",
            [
                ConsumerBinding(
                    "inventory.order_created", ("OrderCreated",), "inv", factory
                )
            ],
            _sf(),
        )
        await _connect(c)
        m = _msg(body=json.dumps({"k": "v"}).encode(), et="OrderCreated", aid="a1")
        m.message_id = "evt-456"
        with caplog.at_level(logging.ERROR, logger="app.shared.messaging.consumer"):
            await c._handle_message(m)
        m.nack.assert_awaited_once_with(requeue=True)
        m.ack.assert_not_awaited()
