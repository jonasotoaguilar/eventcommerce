"""ConfirmOrder use case."""

from uuid import UUID

from app.modules.orders.domain.errors.domain_errors import InvalidStateTransitionError
from app.modules.orders.domain.repositories.repository import OrderRepository
from app.modules.orders.domain.services.order_domain_service import can_transition


class ConfirmOrder:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID) -> None:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            raise InvalidStateTransitionError("Order not found")
        if not can_transition(order.status, "confirmed"):
            raise InvalidStateTransitionError(
                f"Cannot confirm order in status {order.status}"
            )
        order.status = "confirmed"
        await self._repository.save(order)
