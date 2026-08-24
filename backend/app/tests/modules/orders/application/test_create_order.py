"""Tests for CreateOrder use case."""

import pytest

from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.domain.entities import OrderItem
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class TestCreateOrder:
    @pytest.mark.asyncio
    async def test_creates_order_with_items_and_outbox(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        use_case = CreateOrder(order_repo, event_repo, outbox_repo)

        order = await use_case.execute(
            customer_id="cus_1",
            items=[OrderItem(product_id="prod_1", quantity=2)],
        )

        assert order.status == "pending"
        assert order.customer_id == "cus_1"
        assert len(order.items) == 1
        assert order.items[0].product_id == "prod_1"

        # Verify persisted
        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "pending"

        # Verify outbox
        pending = await outbox_repo.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].event_type == "OrderCreated"
        assert pending[0].aggregate_id == str(order.id)
        assert pending[0].payload == {
            "customer_id": "cus_1",
            "items": [{"product_id": "prod_1", "quantity": 2}],
        }

        # Verify timeline event
        timeline = await event_repo.get_timeline(
            aggregate_type="order", aggregate_id=str(order.id)
        )
        assert len(timeline) == 1
        assert timeline[0].event_type == "OrderCreated"
        assert timeline[0].payload == {
            "customer_id": "cus_1",
            "items": [{"product_id": "prod_1", "quantity": 2}],
        }

    @pytest.mark.asyncio
    async def test_serializes_multiple_order_items_in_created_payload(
        self, db_session
    ) -> None:
        use_case = CreateOrder(
            SqlAlchemyOrderRepository(db_session),
            SqlAlchemyEventRepository(db_session),
            SqlAlchemyOutboxRepository(db_session),
        )

        await use_case.execute(
            customer_id="cus_2",
            items=[
                OrderItem(product_id="prod_1", quantity=1),
                OrderItem(product_id="prod_2", quantity=3),
            ],
        )

        pending = await SqlAlchemyOutboxRepository(db_session).get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].payload == {
            "customer_id": "cus_2",
            "items": [
                {"product_id": "prod_1", "quantity": 1},
                {"product_id": "prod_2", "quantity": 3},
            ],
        }

    @pytest.mark.asyncio
    async def test_creates_order_without_items_raises(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        use_case = CreateOrder(order_repo, event_repo, outbox_repo)

        with pytest.raises(ValueError, match="at least one item"):
            await use_case.execute(customer_id="cus_1", items=[])
