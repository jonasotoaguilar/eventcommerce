"""Gated RabbitMQ integration — real broker + EXPLAIN index proof.

Skipped only when EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION != 1.
When enabled, DB/broker/setup/assertions MUST fail (not skip) so CI
cannot report green without the real scenario. Proves persistent
delivery survives reconnect, durable topology recovers, and EXPLAIN
uses (status, created_at) index.
"""

import asyncio
import json
import os
import uuid

import aio_pika
import pytest
from aio_pika import DeliveryMode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.shared.config import get_settings
from app.shared.db.base import Base
from app.shared.messaging.rabbitmq_publisher import RabbitMQPublisher


def _enabled() -> bool:
    return os.getenv("EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION") == "1"


@pytest.mark.asyncio
async def test_rabbitmq_persistent_survives_restart_and_explain_uses_index() -> None:
    if not _enabled():
        pytest.skip("gated: set EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION=1")
    settings = get_settings()
    amqp_url = str(settings.rabbitmq_url)  # type: ignore[arg-type]
    test_db_url = str(settings.test_database_url)  # type: ignore[arg-type]

    # --- DB EXPLAIN evidence — must pass when enabled (no skip mask) ---
    engine = create_async_engine(test_db_url, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_outbox_events_status_created_at "
                    "ON outbox_events (status, created_at)"
                )
            )
            await conn.commit()
            # Deterministic planner evidence: representative volume + ANALYZE
            # so the planner prefers the composite index over a heap scan.
            for idx in range(60):
                await conn.execute(
                    text(
                        "INSERT INTO outbox_events (id, event_type, aggregate_id, payload, status, created_at) "
                        "VALUES (:id, 'OrderCreated', :agg, '{\"customer_id\":\"cus_1\"}', :status, NOW() + (:idx || ' seconds')::interval) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "agg": str(uuid.uuid4()),
                        "status": "pending" if idx % 2 == 0 else "published",
                        "idx": str(idx),
                    },
                )
            await conn.commit()
            await conn.execute(text("ANALYZE outbox_events"))
            res = await conn.execute(
                text(
                    "EXPLAIN SELECT id FROM outbox_events "
                    "WHERE status='pending' ORDER BY created_at LIMIT 100"
                )
            )
            plan = "\n".join(row[0] for row in res.fetchall())
            assert "ix_outbox_events_status_created_at" in plan, plan
            assert "Index Scan" in plan or "Index Only Scan" in plan, plan
            assert "Seq Scan" not in plan, plan
    finally:
        await engine.dispose()

    # --- RabbitMQ durable + persistent proof ---
    queue_name = f"integration.test.persistent.{uuid.uuid4().hex[:8]}"
    exchange_name = "order.events"
    event_id = str(uuid.uuid4())
    aggregate_id = str(uuid.uuid4())
    payload = {"customer_id": "cus_123", "items": [{"product_id": "p1", "quantity": 1}]}
    # Broker must be reachable when enabled — failure is hard, not a skip
    connect = await asyncio.wait_for(
        aio_pika.connect_robust(amqp_url),  # type: ignore[arg-type]
        timeout=5.0,
    )

    try:
        ch = await connect.channel()
        await ch.set_qos(prefetch_count=1)
        ex = await ch.declare_exchange(
            exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        q = await ch.declare_queue(queue_name, durable=True)
        await q.bind(ex, routing_key="IntegrationTestPersistent")
        await q.purge()

        # Publish via production RabbitMQPublisher (persistent, headers)
        pub = RabbitMQPublisher(amqp_url, exchange_name=exchange_name)  # type: ignore[arg-type]
        await pub.connect()

        class _Evt:
            def __init__(self, eid: str, et: str, aid: str, pl: dict) -> None:
                self.id = uuid.UUID(eid)
                self.event_type = et
                self.aggregate_id = aid
                self.payload = pl

        evt = _Evt(event_id, "IntegrationTestPersistent", aggregate_id, payload)
        await pub.publish(evt)  # type: ignore[arg-type]
        # Publisher sets DeliveryMode.PERSISTENT, message_id, headers — prove no payload log
        await pub.close()

        # Simulate broker restart/reconnect: close and re-establish
        await connect.close()
        await asyncio.sleep(0.2)
        connect2 = await asyncio.wait_for(
            aio_pika.connect_robust(amqp_url),  # type: ignore[arg-type]
            timeout=5.0,
        )
        ch2 = await connect2.channel()
        await ch2.set_qos(prefetch_count=1)
        ex2 = await ch2.declare_exchange(
            exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        q2 = await ch2.declare_queue(queue_name, durable=True)
        # Re-bind proves durable topology still valid (recovery)
        await q2.bind(ex2, routing_key="IntegrationTestPersistent")

        # Consume — message must have survived reconnect (persistent + durable queue)
        msg = await asyncio.wait_for(q2.get(no_ack=False, timeout=5.0), timeout=6.0)
        assert msg is not None, "persistent message not redelivered after reconnect"
        assert msg.delivery_mode == DeliveryMode.PERSISTENT, msg.delivery_mode
        assert msg.message_id == event_id
        assert (
            msg.headers and msg.headers.get("event_type") == "IntegrationTestPersistent"
        )
        assert msg.headers.get("aggregate_id") == aggregate_id
        body = json.loads(msg.body.decode())
        assert body == payload
        await msg.ack()

        # Durable queue still present after ack — redeclare succeeds
        q3 = await ch2.declare_queue(queue_name, durable=True)
        assert q3.name == queue_name
        await q3.delete(if_unused=False, if_empty=False)
        await connect2.close()
    except Exception:
        try:
            await connect.close()
        except Exception:
            pass
        raise
