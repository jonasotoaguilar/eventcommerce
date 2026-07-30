"""Tests for ConfirmOrder use case."""

from uuid import uuid4

import pytest

from app.modules.orders.application.confirm_order import ConfirmOrder
from app.modules.orders.domain.errors import (
    InvalidStateTransitionError,
    OrderNotFoundError,
)
from app.modules.orders.domain.entities import Order
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)


class TestConfirmOrder:
    @pytest.mark.asyncio
    async def test_confirms_pending_order(self, db_session) -> None:
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

        use_case = ConfirmOrder(repo)
        await use_case.execute(order.id)

        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_order_raises(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        use_case = ConfirmOrder(repo)

        with pytest.raises(OrderNotFoundError):
            await use_case.execute(uuid4())

    @pytest.mark.asyncio
    async def test_confirm_cancelled_order_raises(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="cancelled",
            cancel_reason="out_of_stock",
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        await repo.save(order)

        use_case = ConfirmOrder(repo)
        with pytest.raises(InvalidStateTransitionError):
            await use_case.execute(order.id)
