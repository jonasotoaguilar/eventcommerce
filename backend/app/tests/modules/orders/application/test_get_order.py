"""Tests for GetOrder use case."""

from uuid import uuid4

import pytest

from app.modules.orders.application.get_order import GetOrder
from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.entities import Order
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)


class TestGetOrder:
    @pytest.mark.asyncio
    async def test_get_existing_order(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        await repo.save(order)

        use_case = GetOrder(repo)
        found = await use_case.execute(order.id)

        assert found.id == order.id
        assert found.customer_id == "cus_1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_order_raises(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        use_case = GetOrder(repo)

        with pytest.raises(OrderNotFoundError):
            await use_case.execute(uuid4())
