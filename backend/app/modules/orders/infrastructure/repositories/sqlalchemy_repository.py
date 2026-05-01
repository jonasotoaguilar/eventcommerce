"""SQLAlchemy implementation of OrderRepository."""
from uuid import UUID

from app.modules.orders.domain.entities.order import Order
from app.modules.orders.domain.repositories.repository import OrderRepository


class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: object) -> None:
        self._session = session

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return None

    async def save(self, order: Order) -> None:
        pass

