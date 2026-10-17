"""Contract tests for InventoryRepository.list_by_product_ids (U2)."""

import pytest

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


class TestListByProductIds:
    @pytest.mark.asyncio
    async def test_returns_matching_rows(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_a", available_quantity=5, reserved_quantity=1)
        )
        await repo.save(
            Inventory(product_id="prod_b", available_quantity=0, reserved_quantity=0)
        )

        rows = await repo.list_by_product_ids(["prod_a", "prod_b", "prod_missing"])

        by_product = {row.product_id: row for row in rows}
        assert set(by_product) == {"prod_a", "prod_b"}
        assert by_product["prod_a"].available_quantity == 5
        assert by_product["prod_a"].reserved_quantity == 1

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        assert await repo.list_by_product_ids([]) == []
