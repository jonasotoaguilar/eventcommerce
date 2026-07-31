"""Outbox repository for reliable event publishing."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.messaging.models import OutboxEventModel


class OutboxEvent:
    def __init__(self, orm: OutboxEventModel) -> None:
        self._orm = orm

    @property
    def id(self) -> UUID:
        return self._orm.id

    @property
    def event_type(self) -> str:
        return self._orm.event_type

    @property
    def aggregate_id(self) -> str:
        return self._orm.aggregate_id

    @property
    def payload(self) -> dict:
        return self._orm.payload

    @property
    def status(self) -> str:
        return self._orm.status


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, event_type: str, aggregate_id: str, payload: dict) -> None:
        orm = OutboxEventModel(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            status="pending",
        )
        self._session.add(orm)
        await self._session.flush()

    async def get_pending(self, limit: int = 100) -> list[OutboxEvent]:
        result = await self._session.execute(
            select(OutboxEventModel)
            .where(OutboxEventModel.status == "pending")
            .order_by(OutboxEventModel.created_at)
            .limit(limit)
        )
        return [OutboxEvent(row) for row in result.scalars().all()]

    async def mark_published(self, event_id: UUID) -> None:
        result = await self._session.execute(
            select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        )
        orm = result.scalar_one_or_none()
        if orm is not None:
            orm.status = "published"
            orm.published_at = datetime.now(timezone.utc)
            await self._session.flush()
