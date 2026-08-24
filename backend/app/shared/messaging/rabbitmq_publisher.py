"""RabbitMQ publisher implementation using aio-pika."""

import json
import logging
from typing import Any

import aio_pika
from aio_pika import DeliveryMode

from app.shared.messaging.outbox_repository import OutboxEvent

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    def __init__(self, amqp_url: str, exchange_name: str = "order.events") -> None:
        self._amqp_url = amqp_url
        self._exchange_name = exchange_name
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def publish(self, event: OutboxEvent) -> None:
        if self._exchange is None:
            raise RuntimeError("Publisher not connected. Call connect() first.")
        message = aio_pika.Message(
            body=json.dumps(event.payload).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(event.id),
            headers={
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
            },
        )
        await self._exchange.publish(message, routing_key=event.event_type)
        logger.info(
            "rabbitmq_publish event_id=%s event_type=%s aggregate_id=%s",
            event.id,
            event.event_type,
            event.aggregate_id,
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
