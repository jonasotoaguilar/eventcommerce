"""GetOrderTimeline use case."""

from uuid import UUID


class GetOrderTimeline:
    async def execute(self, order_id: UUID) -> list[dict]:
        return []
