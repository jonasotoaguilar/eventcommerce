"""Tests for CancelOrder use case."""

from uuid import uuid4

import pytest

from app.modules.orders.application.cancel_order import CancelOrder
from app.modules.orders.domain.entities import Order
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancels_existing_order(self, db_session) -> None:
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

        use_case = CancelOrder(repo)
        await use_case.execute(order.id, "customer_request")

        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "cancelled"
        assert found.cancel_reason == "customer_request"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_does_nothing(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        use_case = CancelOrder(repo)
        await use_case.execute(uuid4(), "customer_request")
