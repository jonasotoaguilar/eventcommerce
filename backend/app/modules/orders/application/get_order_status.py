"""GetOrderStatus use case — orders-owned implementation of inventory port."""

from uuid import UUID

from app.modules.inventory.application.order_status import OrderStatusQuery
from app.modules.orders.domain.repository import OrderRepository


class GetOrderStatus(OrderStatusQuery):
    """Reads order status through the orders repository."""

    def __init__(self, order_repository: OrderRepository) -> None:
        self._repository = order_repository

    async def get_status(self, order_id: UUID) -> str | None:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            return None
        return order.status
