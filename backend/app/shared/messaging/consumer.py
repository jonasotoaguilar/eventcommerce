import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

import aio_pika
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsumerBinding:
    queue: str
    event_types: tuple[str, ...]
    consumer_name: str
    handler_factory: Callable[[AsyncSession], Callable[..., Awaitable[Any]]]

    def __post_init__(self) -> None:
        if not self.queue:
            raise ValueError("queue must not be empty")
        if not self.event_types:
            raise ValueError("event_types must not be empty")
        if not self.consumer_name:
            raise ValueError("consumer_name must not be empty")
        if not callable(self.handler_factory):
            raise ValueError("handler_factory must be callable")


class MessageConsumer:
    def __init__(
        self,
        amqp_url: str,
        bindings: Sequence[ConsumerBinding],
        session_factory: async_sessionmaker[AsyncSession],
        exchange_name: str = "order.events",
    ) -> None:
        if not bindings:
            raise ValueError("at least one binding is required")
        seen_q: set[str] = set()
        seen_t: set[str] = set()
        for b in bindings:
            if b.queue in seen_q:
                raise ValueError(f"duplicate queue: {b.queue}")
            seen_q.add(b.queue)
            for et in b.event_types:
                if et in seen_t:
                    raise ValueError(f"duplicate event_type: {et}")
                seen_t.add(et)
        self._amqp_url = amqp_url
        self._exchange_name = exchange_name
        self._bindings = list(bindings)
        self._session_factory = session_factory
        self._event_map: dict[str, ConsumerBinding] = {}
        for b in self._bindings:
            for et in b.event_types:
                self._event_map[et] = b
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None
        self._queues: list[Any] = []

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)
        self._exchange = await self._channel.declare_exchange(
            self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self._queues = []
        for b in self._bindings:
            q = await self._channel.declare_queue(b.queue, durable=True)
            for rk in b.event_types:
                await q.bind(self._exchange, routing_key=rk)
            self._queues.append(q)

    async def start(self) -> None:
        if not self._queues:
            raise RuntimeError("consumer not connected: call connect() first")
        for q in self._queues:
            await q.consume(self._handle_message, no_ack=False)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def _handle_message(self, message: Any) -> None:
        headers = getattr(message, "headers", None) or {}
        event_type = headers.get("event_type") if isinstance(headers, dict) else None
        aggregate_id = (
            headers.get("aggregate_id") if isinstance(headers, dict) else None
        )
        message_id = getattr(message, "message_id", None)
        if not message_id or not event_type or not aggregate_id:
            logger.warning(
                "consumer_malformed_message event_id=%s event_type=%s queue=%s",
                message_id,
                event_type,
                "unknown",
            )
            await message.ack()
            return
        binding = self._event_map.get(event_type)
        if binding is None:
            logger.warning(
                "consumer_unknown_event_type event_type=%s event_id=%s aggregate_id=%s",
                event_type,
                message_id,
                aggregate_id,
            )
            await message.ack()
            return
        try:
            body = getattr(message, "body", b"")
            if body is None:
                raise ValueError("empty body")
            payload = json.loads(body)  # type: ignore[arg-type]
        except Exception:
            logger.warning(
                "consumer_malformed_payload event_id=%s event_type=%s queue=%s",
                message_id,
                event_type,
                binding.queue,
            )
            await message.ack()
            return
        if not isinstance(payload, dict):
            logger.warning(
                "consumer_malformed_payload_not_object event_id=%s event_type=%s queue=%s",
                message_id,
                event_type,
                binding.queue,
            )
            await message.ack()
            return
        logger.info(
            "consumer_dispatch event_id=%s event_type=%s aggregate_id=%s queue=%s",
            message_id,
            event_type,
            aggregate_id,
            binding.queue,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    handler = binding.handler_factory(session)
                    await handler(
                        payload=payload,
                        event_id=message_id,
                        event_type=event_type,
                        aggregate_id=aggregate_id,
                    )
            await message.ack()
            logger.info(
                "consumer_acked event_id=%s event_type=%s queue=%s",
                message_id,
                event_type,
                binding.queue,
            )
        except Exception:
            logger.exception(
                "consumer_handler_failed event_id=%s event_type=%s queue=%s",
                message_id,
                event_type,
                binding.queue,
            )
            await message.nack(requeue=True)
