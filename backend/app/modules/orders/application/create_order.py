"""CreateOrder use case."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.modules.orders.domain.entities.order import Order
from app.modules.orders.domain.value_objects.order_item import OrderItem


class CreateOrder:
    async def execute(self, customer_id: str, items: list[OrderItem]) -> Order:
        return Order(
            id=uuid4(),
            customer_id=customer_id,
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

