"""Idempotency store using processed_events table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.messaging.models import ProcessedEventModel


class ProcessedEventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_processed(self, event_id: str, consumer_name: str) -> bool:
        result = await self._session.execute(
            select(ProcessedEventModel).where(
                ProcessedEventModel.event_id == event_id,
                ProcessedEventModel.consumer_name == consumer_name,
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, event_id: str, consumer_name: str) -> None:
        if await self.is_processed(event_id, consumer_name):
            return
        orm = ProcessedEventModel(
            event_id=event_id,
            consumer_name=consumer_name,
        )
        self._session.add(orm)
        await self._session.flush()
