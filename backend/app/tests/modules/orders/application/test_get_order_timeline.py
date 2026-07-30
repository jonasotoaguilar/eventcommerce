"""Tests for GetOrderTimeline use case."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.orders.application.get_order_timeline import GetOrderTimeline
from app.modules.orders.domain.entities import Order
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository


class TestGetOrderTimeline:
    @pytest.mark.asyncio
    async def test_returns_timeline(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        use_case = GetOrderTimeline(event_repo)
        order_id = uuid4()

        order = Order(
            id=order_id,
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[],
        )
        await order_repo.save(order)

        await event_repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id=str(order_id),
            event_type="OrderCreated",
            occurred_at=datetime.now(timezone.utc),
            payload={
                "customer_id": "cus_1",
                "items": [{"product_id": "prod_1", "quantity": 1}],
            },
        )

        timeline = await use_case.execute(order_id)
        assert len(timeline) == 1
        assert timeline[0]["event_type"] == "OrderCreated"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self, db_session) -> None:
        event_repo = SqlAlchemyEventRepository(db_session)
        use_case = GetOrderTimeline(event_repo)
        timeline = await use_case.execute(uuid4())
        assert timeline == []
