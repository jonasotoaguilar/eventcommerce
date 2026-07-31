"""Tests for ReserveInventory use case."""

from uuid import uuid4

import pytest

from app.modules.inventory.application.reserve_inventory import ReserveInventory
from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


class TestReserveInventory:
    @pytest.mark.asyncio
    async def test_reserves_stock(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        )

        use_case = ReserveInventory(repo)
        await use_case.execute(order_id=uuid4(), product_id="prod_1", quantity=3)

        inv = await repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 7
        assert inv.reserved_quantity == 3

    @pytest.mark.asyncio
    async def test_insufficient_stock_raises(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_1", available_quantity=1, reserved_quantity=0)
        )

        use_case = ReserveInventory(repo)
        with pytest.raises(InsufficientStockError):
            await use_case.execute(order_id=uuid4(), product_id="prod_1", quantity=3)

    @pytest.mark.asyncio
    async def test_product_not_found_raises(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        use_case = ReserveInventory(repo)
        with pytest.raises(InsufficientStockError):
            await use_case.execute(order_id=uuid4(), product_id="missing", quantity=1)
