"""Tests for RabbitMQPublisher."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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
