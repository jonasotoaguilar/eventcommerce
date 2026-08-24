"""Tests for RabbitMQPublisher."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aio_pika import DeliveryMode

from app.shared.messaging.outbox_repository import OutboxEvent
from app.shared.messaging.rabbitmq_publisher import RabbitMQPublisher


class TestRabbitMQPublisher:
    @pytest.mark.asyncio
    async def test_connect_declares_exchange(self) -> None:
        with patch(
            "app.shared.messaging.rabbitmq_publisher.aio_pika.connect_robust"
        ) as mock_connect:
            mock_conn = AsyncMock()
            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            mock_channel.declare_exchange.return_value = mock_exchange
            mock_conn.channel.return_value = mock_channel
            mock_connect.return_value = mock_conn

            publisher = RabbitMQPublisher("amqp://guest:guest@localhost/")
            await publisher.connect()

            mock_connect.assert_awaited_once_with("amqp://guest:guest@localhost/")
            mock_channel.declare_exchange.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_sends_message(self) -> None:
        with patch(
            "app.shared.messaging.rabbitmq_publisher.aio_pika.connect_robust"
        ) as mock_connect:
            mock_conn = AsyncMock()
            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            mock_channel.declare_exchange.return_value = mock_exchange
            mock_conn.channel.return_value = mock_channel
            mock_connect.return_value = mock_conn

            publisher = RabbitMQPublisher("amqp://guest:guest@localhost/")
            await publisher.connect()

            event = MagicMock(spec=OutboxEvent)
            event.id = uuid4()
            event.event_type = "OrderCreated"
            event.aggregate_id = str(uuid4())
            event.payload = {"customer_id": "cus_1"}

            await publisher.publish(event)

            mock_exchange.publish.assert_awaited_once()
            call_args = mock_exchange.publish.await_args
            message = call_args[0][0]
            routing_key = call_args[1]["routing_key"]
            assert routing_key == "OrderCreated"
            assert message.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_publish_without_connect_raises(self) -> None:
        publisher = RabbitMQPublisher("amqp://guest:guest@localhost/")
        event = MagicMock(spec=OutboxEvent)
        with pytest.raises(RuntimeError, match="not connected"):
            await publisher.publish(event)

    @pytest.mark.asyncio
    async def test_publish_persistent_headers_no_payload_log(self, caplog) -> None:
        with patch(
            "app.shared.messaging.rabbitmq_publisher.aio_pika.connect_robust"
        ) as mock_connect:
            mock_conn = AsyncMock()
            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            mock_channel.declare_exchange.return_value = mock_exchange
            mock_conn.channel.return_value = mock_channel
            mock_connect.return_value = mock_conn
            publisher = RabbitMQPublisher("amqp://guest:guest@localhost/")
            await publisher.connect()
            eid = uuid4()
            aid = str(uuid4())
            event = MagicMock(spec=OutboxEvent)
            event.id = eid
            event.event_type = "OrderCreated"
            event.aggregate_id = aid
            event.payload = {"customer_id": "cus_secret_123", "items": []}
            with caplog.at_level(
                logging.INFO, logger="app.shared.messaging.rabbitmq_publisher"
            ):
                await publisher.publish(event)
            msg = mock_exchange.publish.await_args[0][0]
            assert msg.delivery_mode == DeliveryMode.PERSISTENT
            assert msg.message_id == str(eid)
            assert msg.headers["event_type"] == "OrderCreated"
            assert msg.headers["aggregate_id"] == aid
            assert "cus_secret_123" not in caplog.text
