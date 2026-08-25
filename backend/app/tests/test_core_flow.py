"""End-to-end integration test for Phase 1 core flow."""

from uuid import uuid4

import pytest

from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.application.get_order_status import GetOrderStatus
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.domain.entities import OrderItem
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository
from app.shared.messaging.idempotency import ProcessedEventStore


class TestCoreFlow:
    @pytest.mark.asyncio
    async def test_happy_path_confirm_order(self, db_session) -> None:
        # Setup
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        idempotency = ProcessedEventStore(db_session)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        )

        # Step 1: Create order
        create_uc = CreateOrder(order_repo, event_repo, outbox_repo)
        order = await create_uc.execute(
            customer_id="cus_1",
            items=[OrderItem(product_id="prod_1", quantity=2)],
        )
        await db_session.commit()

        # Step 2: Process inventory reservation
        inv_event_id = str(uuid4())
        order_status = GetOrderStatus(order_repo)  # type: ignore[arg-type]
        inv_uc = ProcessInventoryReservation(
            inv_repo, outbox_repo, idempotency, order_status
        )
        await inv_uc.execute(
            event_id=inv_event_id,
            order_id=str(order.id),
            items=[{"product_id": "prod_1", "quantity": 2}],
        )
        await db_session.commit()

        # Step 3: Process inventory result -> confirm order
        result_event_id = str(uuid4())
        result_uc = ProcessOrderInventoryResult(
            order_repo, event_repo, outbox_repo, idempotency
        )
        await result_uc.execute(
            event_id=result_event_id, order_id=order.id, result="reserved"
        )
        await db_session.commit()

        # Verify
        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "confirmed"

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 8
        assert inv.reserved_quantity == 2

    @pytest.mark.asyncio
    async def test_insufficient_stock_cancels_order(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        idempotency = ProcessedEventStore(db_session)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=1, reserved_quantity=0)
        )

        create_uc = CreateOrder(order_repo, event_repo, outbox_repo)
        order = await create_uc.execute(
            customer_id="cus_1",
            items=[OrderItem(product_id="prod_1", quantity=2)],
        )
        await db_session.commit()

        inv_event_id = str(uuid4())
        order_status = GetOrderStatus(order_repo)  # type: ignore[arg-type]
        inv_uc = ProcessInventoryReservation(
            inv_repo, outbox_repo, idempotency, order_status
        )
        await inv_uc.execute(
            event_id=inv_event_id,
            order_id=str(order.id),
            items=[{"product_id": "prod_1", "quantity": 2}],
        )
        await db_session.commit()

        result_event_id = str(uuid4())
        result_uc = ProcessOrderInventoryResult(
            order_repo, event_repo, outbox_repo, idempotency
        )
        await result_uc.execute(
            event_id=result_event_id, order_id=order.id, result="rejected"
        )
        await db_session.commit()

        found = await order_repo.get_by_id(order.id)
        assert found is not None
        assert found.status == "cancelled"
        assert found.cancel_reason == "insufficient_stock"

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 1
        assert inv.reserved_quantity == 0

    @pytest.mark.asyncio
    async def test_idempotency_no_duplicate_inventory(self, db_session) -> None:
        order_repo = SqlAlchemyOrderRepository(db_session)
        event_repo = SqlAlchemyEventRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        idempotency = ProcessedEventStore(db_session)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=5, reserved_quantity=0)
        )

        create_uc = CreateOrder(order_repo, event_repo, outbox_repo)
        order = await create_uc.execute(
            customer_id="cus_1",
            items=[OrderItem(product_id="prod_1", quantity=2)],
        )
        await db_session.commit()

        inv_event_id = str(uuid4())
        order_status = GetOrderStatus(order_repo)  # type: ignore[arg-type]
        inv_uc = ProcessInventoryReservation(
            inv_repo, outbox_repo, idempotency, order_status
        )
        # Simulate duplicate event processing
        await inv_uc.execute(
            event_id=inv_event_id,
            order_id=str(order.id),
            items=[{"product_id": "prod_1", "quantity": 2}],
        )
        await db_session.commit()
        await inv_uc.execute(
            event_id=inv_event_id,
            order_id=str(order.id),
            items=[{"product_id": "prod_1", "quantity": 2}],
        )
        await db_session.commit()

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        # Idempotency guard prevents double-reservation
        assert inv.available_quantity == 3
        assert inv.reserved_quantity == 2
