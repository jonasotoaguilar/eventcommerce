"""CancelOrder use case."""

from uuid import UUID

from app.modules.orders.domain.repositories.repository import OrderRepository


class CancelOrder:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID, reason: str) -> None:
        order = await self._repository.get_by_id(order_id)
        if order is not None:
            order.status = "cancelled"
            order.cancel_reason = reason
            await self._repository.save(order)
