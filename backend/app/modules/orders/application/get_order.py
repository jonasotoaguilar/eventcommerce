"""GetOrder use case."""
from uuid import UUID

from app.modules.orders.domain.entities.order import Order
from app.modules.orders.domain.errors.domain_errors import OrderNotFoundError
from app.modules.orders.domain.repositories.repository import OrderRepository


class GetOrder:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID) -> Order:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

