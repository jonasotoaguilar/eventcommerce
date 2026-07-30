"""Integration tests for SQLAlchemy order repository."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)


class TestSqlAlchemyOrderRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[OrderItem(product_id="prod_1", quantity=2)],
        )
        await repo.save(order)

        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.id == order.id
        assert found.customer_id == "cus_1"
        assert found.status == "pending"
        assert len(found.items) == 1
        assert found.items[0].product_id == "prod_1"
        assert found.items[0].quantity == 2

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        found = await repo.get_by_id(uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_update_status(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[],
        )
        await repo.save(order)
        order.confirm()
        await repo.save(order)

        found = await repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"
