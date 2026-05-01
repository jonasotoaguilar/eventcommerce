"""Order repository protocol."""

from typing import Protocol
from uuid import UUID

from app.modules.orders.domain.entities.order import Order


class OrderRepository(Protocol):
    async def get_by_id(self, order_id: UUID) -> Order | None: ...
    async def save(self, order: Order) -> None: ...
