"""Contract tests for OrderRepository.list_queue (operator queue read)."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)


def _order(
    status: str,
    created_at: datetime,
    quantity: int = 1,
    customer_id: str = "cus_1",
) -> Order:
    return Order(
        id=uuid4(),
        customer_id=customer_id,
        status=status,
        cancel_reason=None,
        created_at=created_at,
        updated_at=created_at,
        items=[OrderItem(product_id="prod_1", quantity=quantity)],
    )


async def _seed(repo: SqlAlchemyOrderRepository, *orders: Order) -> None:
    for order in orders:
        await repo.save(order)


class TestListQueue:
    @pytest.mark.asyncio
    async def test_returns_all_without_filters_ordered_by_created_at(
        self, db_session
    ) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        newer = _order("pending", datetime(2024, 5, 2, 12, 0, 0))
        older = _order("confirmed", datetime(2024, 5, 1, 12, 0, 0))
        await _seed(repo, newer, older)

        rows = await repo.list_queue()

        assert [r.id for r in rows] == [older.id, newer.id]

    @pytest.mark.asyncio
    async def test_filters_by_status(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        pending = _order("pending", datetime(2024, 5, 1, 12, 0, 0))
        confirmed = _order("confirmed", datetime(2024, 5, 2, 12, 0, 0))
        await _seed(repo, pending, confirmed)

        rows = await repo.list_queue(status="confirmed")

        assert [r.id for r in rows] == [confirmed.id]

    @pytest.mark.asyncio
    async def test_created_from_inclusive_created_to_exclusive(
        self, db_session
    ) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        first = _order("pending", datetime(2024, 5, 1, 12, 0, 0))
        second = _order("pending", datetime(2024, 5, 2, 12, 0, 0))
        third = _order("pending", datetime(2024, 5, 3, 12, 0, 0))
        await _seed(repo, first, second, third)

        rows = await repo.list_queue(
            created_from=datetime(2024, 5, 2, 12, 0, 0),
            created_to=datetime(2024, 5, 3, 12, 0, 0),
        )

        assert [r.id for r in rows] == [second.id]

    @pytest.mark.asyncio
    async def test_limit_offset_paginate(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        orders = [
            _order("pending", datetime(2024, 5, day, 12, 0, 0)) for day in (1, 2, 3)
        ]
        await _seed(repo, *orders)

        rows = await repo.list_queue(limit=1, offset=1)

        assert [r.id for r in rows] == [orders[1].id]

    @pytest.mark.asyncio
    async def test_row_carries_items_for_item_count(self, db_session) -> None:
        repo = SqlAlchemyOrderRepository(db_session)
        order = _order("pending", datetime(2024, 5, 1, 12, 0, 0), quantity=2)
        await _seed(repo, order)

        (row,) = await repo.list_queue()

        assert row.id == order.id
        assert sum(item.quantity for item in row.items) == 2
