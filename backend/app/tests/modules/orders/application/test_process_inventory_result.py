"""Tests for ProcessOrderInventoryResult use case."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class TestProcessOrderInventoryResult:
    @pytest.mark.asyncio
    async def test_confirms_order_on_inventory_reserved(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessOrderInventoryResult(
            order_repo, event_repo, outbox_repo, idempotency
        )

        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[OrderItem(product_id="prod_1", quantity=1)],
        )
        await order_repo.save(order)

        await use_case.execute(
            event_id=str(uuid4()),
            order_id=order.id,
            result="reserved",
        )

        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"

        pending = await outbox_repo.get_pending(limit=10)
        assert any(e.event_type == "OrderConfirmed" for e in pending)

        timeline = await event_repo.get_timeline(
            aggregate_type="order", aggregate_id=str(order.id)
        )
        assert any(e.event_type == "InventoryReserved" for e in timeline)

    @pytest.mark.asyncio
    async def test_cancels_order_on_inventory_rejected(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessOrderInventoryResult(
            order_repo, event_repo, outbox_repo, idempotency
        )

        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[OrderItem(product_id="prod_1", quantity=1)],
        )
        await order_repo.save(order)

        await use_case.execute(
            event_id=str(uuid4()),
            order_id=order.id,
            result="rejected",
        )

        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "cancelled"
        assert found.cancel_reason == "insufficient_stock"

        pending = await outbox_repo.get_pending(limit=10)
        assert any(e.event_type == "OrderCancelled" for e in pending)

        timeline = await event_repo.get_timeline(
            aggregate_type="order", aggregate_id=str(order.id)
        )
        assert any(e.event_type == "InventoryRejected" for e in timeline)

    @pytest.mark.asyncio
    async def test_duplicate_event_is_ignored(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessOrderInventoryResult(
            order_repo, event_repo, outbox_repo, idempotency
        )

        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[OrderItem(product_id="prod_1", quantity=1)],
        )
        await order_repo.save(order)

        event_id = str(uuid4())
        await use_case.execute(
            event_id=event_id,
            order_id=order.id,
            result="reserved",
        )
        await db_session.commit()

        # Simulate duplicate delivery
        await use_case.execute(
            event_id=event_id,
            order_id=order.id,
            result="reserved",
        )
        await db_session.commit()

        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"

        pending = await outbox_repo.get_pending(limit=10)
        assert sum(1 for e in pending if e.event_type == "OrderConfirmed") == 1

        timeline = await event_repo.get_timeline(
            aggregate_type="order", aggregate_id=str(order.id)
        )
        assert sum(1 for e in timeline if e.event_type == "InventoryReserved") == 1
