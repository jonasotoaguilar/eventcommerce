"""SQLAlchemy implementation of the shared event store."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.events.models import DomainEventModel
from app.shared.events.repository import TimelineEvent


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        event_id: UUID,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> None:
        orm = DomainEventModel(
            event_id=event_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=self._to_serializable(payload),
            occurred_at=occurred_at,
        )
        self._session.add(orm)
        await self._session.flush()

    async def get_timeline(
        self, aggregate_type: str, aggregate_id: str
    ) -> list[TimelineEvent]:
        result = await self._session.execute(
            select(DomainEventModel)
            .where(DomainEventModel.aggregate_type == aggregate_type)
            .where(DomainEventModel.aggregate_id == aggregate_id)
            .order_by(DomainEventModel.occurred_at)
        )
        return [
            TimelineEvent(
                event_id=row.event_id,
                event_type=row.event_type,
                payload=row.payload,
                occurred_at=row.occurred_at,
            )
            for row in result.scalars().all()
        ]

    def _to_serializable(self, value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._to_serializable(v) for v in value]
        if isinstance(value, dict):
            return {k: self._to_serializable(v) for k, v in value.items()}
        return value
