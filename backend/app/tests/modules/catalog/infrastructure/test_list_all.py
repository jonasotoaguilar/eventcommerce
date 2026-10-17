"""Contract tests for ProductRepository.list_all (U2: operator catalog read).

``list_all`` includes inactive products ordered by product id, unlike
``list_active`` which the public browse keeps using.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)


def _product(product_id: str = "prod_1", **overrides) -> Product:
    now = datetime.now(timezone.utc)
    base: dict = {
        "id": product_id,
        "name": f"Product {product_id}",
        "description": None,
        "price": Decimal("9.99"),
        "currency": "USD",
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Product(**base)


class TestListAll:
    @pytest.mark.asyncio
    async def test_includes_inactive_ordered_by_id(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        await repo.save(_product("prod_b", active=False))
        await repo.save(_product("prod_a"))
        await repo.save(_product("prod_c", active=False))

        products = await repo.list_all()

        assert [p.id for p in products] == ["prod_a", "prod_b", "prod_c"]
        assert [p.active for p in products] == [True, False, False]

    @pytest.mark.asyncio
    async def test_limit_and_offset(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        for pid in ("prod_a", "prod_b", "prod_c"):
            await repo.save(_product(pid))

        assert [p.id for p in await repo.list_all(limit=1, offset=1)] == ["prod_b"]
        assert await repo.list_all(limit=1, offset=10) == []
