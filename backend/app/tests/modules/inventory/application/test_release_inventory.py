"""Tests for ReleaseInventory use case."""

import pytest

from app.modules.inventory.application.release_inventory import ReleaseInventory
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


class TestReleaseInventory:
    @pytest.mark.asyncio
    async def test_releases_stock(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_1", available_quantity=7, reserved_quantity=3)
        )

        use_case = ReleaseInventory(repo)
        await use_case.execute(product_id="prod_1", quantity=2)

        inv = await repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 9
        assert inv.reserved_quantity == 1

    @pytest.mark.asyncio
    async def test_release_nonexistent_product_does_nothing(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        use_case = ReleaseInventory(repo)
        await use_case.execute(product_id="missing", quantity=1)
