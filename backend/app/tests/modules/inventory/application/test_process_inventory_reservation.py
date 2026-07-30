"""Tests for ProcessInventoryReservation use case."""

from uuid import uuid4

import pytest

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.inventory.application.process_inventory_reservation import (
    ProcessInventoryReservation,
)
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository
from app.shared.messaging.idempotency import ProcessedEventStore


class TestProcessInventoryReservation:
    @pytest.mark.asyncio
    async def test_reserves_inventory_and_emits_reserved(self, db_session) -> None:
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessInventoryReservation(inv_repo, outbox_repo, idempotency)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        )

        await use_case.execute(
            event_id=str(uuid4()),
            order_id="order-123",
            items=[{"product_id": "prod_1", "quantity": 3}],
        )

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 7
        assert inv.reserved_quantity == 3

        pending = await outbox_repo.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].event_type == "InventoryReserved"

    @pytest.mark.asyncio
    async def test_insufficient_stock_emits_rejected(self, db_session) -> None:
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessInventoryReservation(inv_repo, outbox_repo, idempotency)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=1, reserved_quantity=0)
        )

        await use_case.execute(
            event_id=str(uuid4()),
            order_id="order-123",
            items=[{"product_id": "prod_1", "quantity": 3}],
        )

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 1
        assert inv.reserved_quantity == 0

        pending = await outbox_repo.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].event_type == "InventoryRejected"

    @pytest.mark.asyncio
    async def test_duplicate_event_is_ignored(self, db_session) -> None:
        inv_repo = SqlAlchemyInventoryRepository(db_session)
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        idempotency = ProcessedEventStore(db_session)
        use_case = ProcessInventoryReservation(inv_repo, outbox_repo, idempotency)

        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        )

        event_id = str(uuid4())
        await use_case.execute(
            event_id=event_id,
            order_id="order-123",
            items=[{"product_id": "prod_1", "quantity": 3}],
        )
        await db_session.commit()

        # Simulate duplicate delivery
        await use_case.execute(
            event_id=event_id,
            order_id="order-123",
            items=[{"product_id": "prod_1", "quantity": 3}],
        )
        await db_session.commit()

        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 7
        assert inv.reserved_quantity == 3

        pending = await outbox_repo.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].event_type == "InventoryReserved"
