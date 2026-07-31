"""GetOrderTimeline use case."""

from uuid import UUID

from app.shared.events.event_repository import SqlAlchemyEventRepository


class GetOrderTimeline:
    def __init__(self, event_repo: SqlAlchemyEventRepository) -> None:
        self._event_repo = event_repo

    async def execute(self, order_id: UUID) -> list[dict]:
        events = await self._event_repo.get_timeline(
            aggregate_type="order",
            aggregate_id=str(order_id),
        )
        return [
            {
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ]
