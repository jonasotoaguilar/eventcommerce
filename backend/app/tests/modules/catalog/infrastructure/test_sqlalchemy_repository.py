"""Infrastructure tests for the catalog product repository (U1)."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import ProductAlreadyExistsError
from app.modules.catalog.infrastructure.models import ProductModel
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)


def _product(product_id: str = "prod_1", **overrides) -> Product:
    now = datetime.now(timezone.utc)
    base: dict = {
        "id": product_id,
        "name": "Workshop Ticket",
        "description": None,
        "price": Decimal("49.99"),
        "currency": "USD",
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Product(**base)


class TestSqlAlchemyProductRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        await repo.save(_product())

        found = await repo.get_by_id("prod_1")
        assert found is not None
        assert found.name == "Workshop Ticket"
        assert found.price == Decimal("49.99")
        assert found.currency == "USD"
        assert found.active is True

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        assert await repo.get_by_id("missing") is None

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        await repo.save(_product())

        await repo.save(_product(name="Renamed", active=False))

        found = await repo.get_by_id("prod_1")
        assert found is not None
        assert found.name == "Renamed"
        assert found.active is False

    @pytest.mark.asyncio
    async def test_list_active_excludes_inactive(self, db_session) -> None:
        repo = SqlAlchemyProductRepository(db_session)
        await repo.save(_product("prod_a"))
        await repo.save(_product("prod_b", active=False))
        await repo.save(_product("prod_c"))

        products = await repo.list_active()
        assert [p.id for p in products] == ["prod_a", "prod_c"]

    def test_model_tablename(self) -> None:
        assert ProductModel.__tablename__ == "catalog_products"

    def test_model_carries_migration_constraints(self) -> None:
        table = cast(Table, ProductModel.__table__)
        names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert {
            "ck_catalog_products_id_len",
            "ck_catalog_products_name_len",
            "ck_catalog_products_price_range",
            "ck_catalog_products_currency",
        } <= names
        assert "ix_catalog_products_active" in {index.name for index in table.indexes}


class _DbApiError(Exception):
    """Minimal DBAPI error stand-in carrying a message and pgcode."""

    def __init__(self, message: str, pgcode: str | None = None) -> None:
        super().__init__(message)
        self.pgcode = pgcode


class _FlushFailingSession:
    """Session stub whose flush raises a canned IntegrityError."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self, *args, **kwargs):
        class _Result:
            @staticmethod
            def scalar_one_or_none():
                return None

        return _Result()

    def add(self, orm) -> None:
        pass

    async def flush(self) -> None:
        raise self._error


def _integrity_error(message: str, pgcode: str | None) -> IntegrityError:
    return IntegrityError(
        "INSERT INTO catalog_products ...", {}, _DbApiError(message, pgcode)
    )


class TestDuplicateRaceMapping:
    @pytest.mark.asyncio
    async def test_pk_conflict_maps_to_already_exists(self) -> None:
        session = _FlushFailingSession(
            _integrity_error(
                'duplicate key value violates unique constraint "catalog_products_pkey"',
                "23505",
            )
        )
        repo = SqlAlchemyProductRepository(cast(AsyncSession, session))
        with pytest.raises(ProductAlreadyExistsError):
            await repo.save(
                Product(
                    id="prod_1",
                    name="A",
                    price=Decimal("1.00"),
                    currency="USD",
                )
            )

    @pytest.mark.asyncio
    async def test_pk_name_matches_without_pgcode(self) -> None:
        session = _FlushFailingSession(
            _integrity_error(
                'duplicate key value violates unique constraint "catalog_products_pkey"',
                None,
            )
        )
        repo = SqlAlchemyProductRepository(cast(AsyncSession, session))
        with pytest.raises(ProductAlreadyExistsError):
            await repo.save(
                Product(
                    id="prod_1",
                    name="A",
                    price=Decimal("1.00"),
                    currency="USD",
                )
            )

    @pytest.mark.asyncio
    async def test_unrelated_conflict_is_reraised(self) -> None:
        error = _integrity_error(
            'duplicate key value violates unique constraint "other_table_pkey"',
            "23505",
        )
        session = _FlushFailingSession(error)
        repo = SqlAlchemyProductRepository(cast(AsyncSession, session))
        with pytest.raises(IntegrityError) as exc_info:
            await repo.save(
                Product(
                    id="prod_1",
                    name="A",
                    price=Decimal("1.00"),
                    currency="USD",
                )
            )
        assert exc_info.value is error
