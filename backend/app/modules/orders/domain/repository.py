"""Order repository protocols."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.orders.domain.entities import Order


class OrderRepository(Protocol):
    async def get_by_id(self, order_id: UUID) -> Order | None: ...
    async def save(self, order: Order) -> None: ...
    async def list_queue(
        self,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Order]: ...
