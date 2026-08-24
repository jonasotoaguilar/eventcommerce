"""Outbox worker for publishing pending events."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class OutboxWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher

    async def run_once(self, batch_size: int = 100) -> int:
        async with self._session_factory.begin() as session:
            outbox = SqlAlchemyOutboxRepository(session)
            events = await outbox.get_pending(limit=batch_size)
            published = 0
            for event in events:
                try:
                    await self._publisher.publish(event)
                except Exception:
                    logger.exception(
                        "outbox_publish_failed event_id=%s event_type=%s "
                        "aggregate_id=%s",
                        event.id,
                        event.event_type,
                        event.aggregate_id,
                    )
                    continue
                await outbox.mark_published(event.id)
                published += 1
            return published
