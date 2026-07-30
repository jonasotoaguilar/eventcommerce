"""Integration tests for SQLAlchemy inventory repository."""

import pytest

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


class TestSqlAlchemyInventoryRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_product(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        inv = Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        await repo.save(inv)

        found = await repo.get_by_product("prod_1")
        assert found is not None
        assert found.available_quantity == 10
        assert found.reserved_quantity == 0

    @pytest.mark.asyncio
    async def test_get_by_product_not_found(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        found = await repo.get_by_product("prod_missing")
        assert found is None

    @pytest.mark.asyncio
    async def test_update_inventory(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        inv = Inventory(product_id="prod_1", available_quantity=10, reserved_quantity=0)
        await repo.save(inv)

        inv.available_quantity = 8
        inv.reserved_quantity = 2
        await repo.save(inv)

        found = await repo.get_by_product("prod_1")
        assert found is not None
        assert found.available_quantity == 8
        assert found.reserved_quantity == 2
