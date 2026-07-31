"""SQLAlchemy implementation of OrderRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.repository import OrderRepository
from app.modules.orders.infrastructure.models import OrderItemModel, OrderModel


class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, order_id: UUID) -> Order | None:
        result = await self._session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    async def save(self, order: Order) -> None:
        result = await self._session.execute(
            select(OrderModel).where(OrderModel.id == order.id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.status = order.status
            existing.cancel_reason = order.cancel_reason
            existing.updated_at = order.updated_at
        else:
            orm = OrderModel(
                id=order.id,
                customer_id=order.customer_id,
                status=order.status,
                cancel_reason=order.cancel_reason,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            orm.items = [
                OrderItemModel(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
                for item in order.items
            ]
            self._session.add(orm)
        await self._session.flush()

    def _to_domain(self, orm: OrderModel) -> Order:
        return Order(
            id=orm.id,
            customer_id=orm.customer_id,
            status=orm.status,
            cancel_reason=orm.cancel_reason,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            items=[
                OrderItem(product_id=i.product_id, quantity=i.quantity)
                for i in orm.items
            ],
        )
