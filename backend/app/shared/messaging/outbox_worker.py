"""Outbox worker for publishing pending events."""

from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class OutboxWorker:
    def __init__(
        self,
        outbox: SqlAlchemyOutboxRepository,
        publisher,
    ) -> None:
        self._outbox = outbox
        self._publisher = publisher

    async def run_once(self, batch_size: int = 100) -> int:
        events = await self._outbox.get_pending(limit=batch_size)
        for event in events:
            await self._publisher.publish(event)
            await self._outbox.mark_published(event.id)
        return len(events)
