"""Application tests for catalog use cases (U1)."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.catalog.application.create_product import CreateProduct
from app.modules.catalog.application.get_product import GetProduct
from app.modules.catalog.application.list_products import ListProducts
from app.modules.catalog.application.update_product import UpdateProduct
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import (
    InvalidProductError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


def _repos(db_session):
    return (
        SqlAlchemyProductRepository(db_session),
        SqlAlchemyInventoryRepository(db_session),
    )


class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_creates_product_and_seeds_inventory_at_zero(
        self, db_session
    ) -> None:
        product_repo, inv_repo = _repos(db_session)
        use_case = CreateProduct(product_repo, inv_repo)

        product = await use_case.execute(
            product_id="prod_1",
            name="Workshop Ticket",
            price=Decimal("49.99"),
            currency="USD",
            description="Day pass",
        )

        assert product.id == "prod_1"
        found = await product_repo.get_by_id("prod_1")
        assert found is not None and found.name == "Workshop Ticket"
        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 0
        assert inv.reserved_quantity == 0

    @pytest.mark.asyncio
    async def test_duplicate_id_raises(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        use_case = CreateProduct(product_repo, inv_repo)
        await use_case.execute(
            product_id="prod_1",
            name="A",
            price=Decimal("1.00"),
            currency="USD",
        )
        with pytest.raises(ProductAlreadyExistsError):
            await use_case.execute(
                product_id="prod_1",
                name="B",
                price=Decimal("2.00"),
                currency="USD",
            )

    @pytest.mark.asyncio
    async def test_invalid_price_raises(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        use_case = CreateProduct(product_repo, inv_repo)
        with pytest.raises(InvalidProductError):
            await use_case.execute(
                product_id="prod_1",
                name="A",
                price=Decimal("10.999"),
                currency="USD",
            )

    @pytest.mark.asyncio
    async def test_existing_inventory_is_not_reset(self, db_session) -> None:
        from app.modules.inventory.domain.entities import Inventory

        product_repo, inv_repo = _repos(db_session)
        await inv_repo.save(
            Inventory(product_id="prod_1", available_quantity=5, reserved_quantity=1)
        )
        use_case = CreateProduct(product_repo, inv_repo)
        await use_case.execute(
            product_id="prod_1",
            name="A",
            price=Decimal("1.00"),
            currency="USD",
        )
        inv = await inv_repo.get_by_product("prod_1")
        assert inv is not None
        assert inv.available_quantity == 5
        assert inv.reserved_quantity == 1


class TestGetProduct:
    @pytest.mark.asyncio
    async def test_returns_active_product(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        await CreateProduct(product_repo, inv_repo).execute(
            product_id="prod_1", name="A", price=Decimal("1.00"), currency="USD"
        )
        product = await GetProduct(product_repo).execute("prod_1")
        assert product.id == "prod_1"

    @pytest.mark.asyncio
    async def test_missing_raises(self, db_session) -> None:
        product_repo, _ = _repos(db_session)
        with pytest.raises(ProductNotFoundError):
            await GetProduct(product_repo).execute("missing")

    @pytest.mark.asyncio
    async def test_inactive_hidden_by_default(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        await CreateProduct(product_repo, inv_repo).execute(
            product_id="prod_1",
            name="A",
            price=Decimal("1.00"),
            currency="USD",
            active=False,
        )
        with pytest.raises(ProductNotFoundError):
            await GetProduct(product_repo).execute("prod_1")


class TestListProducts:
    @pytest.mark.asyncio
    async def test_lists_only_active(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        create = CreateProduct(product_repo, inv_repo)
        await create.execute(
            product_id="prod_active", name="A", price=Decimal("1.00"), currency="USD"
        )
        await create.execute(
            product_id="prod_hidden",
            name="H",
            price=Decimal("1.00"),
            currency="USD",
            active=False,
        )
        products = await ListProducts(product_repo).execute()
        assert [p.id for p in products] == ["prod_active"]


class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_updates_fields(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        await CreateProduct(product_repo, inv_repo).execute(
            product_id="prod_1", name="A", price=Decimal("1.00"), currency="USD"
        )
        updated = await UpdateProduct(product_repo).execute(
            "prod_1", name="B", price=Decimal("2.50"), active=False
        )
        assert updated.name == "B"
        assert updated.price == Decimal("2.50")
        assert updated.active is False

    @pytest.mark.asyncio
    async def test_missing_raises(self, db_session) -> None:
        product_repo, _ = _repos(db_session)
        with pytest.raises(ProductNotFoundError):
            await UpdateProduct(product_repo).execute("missing", name="B")

    @pytest.mark.asyncio
    async def test_invalid_currency_raises(self, db_session) -> None:
        product_repo, inv_repo = _repos(db_session)
        await CreateProduct(product_repo, inv_repo).execute(
            product_id="prod_1", name="A", price=Decimal("1.00"), currency="USD"
        )
        with pytest.raises(InvalidProductError):
            await UpdateProduct(product_repo).execute("prod_1", currency="usd")


class TestConcurrentDuplicateCreation:
    @pytest.mark.asyncio
    async def test_racing_insert_maps_to_stable_conflict(self, engine) -> None:
        """A unique-key race resolves to ProductAlreadyExistsError (API 409).

        Session 1 holds an uncommitted insert of the same id, so session 2's
        check-then-insert either blocks on the row lock and then hits the
        unique violation, or (if scheduled after the commit) sees the row in
        its pre-check. Both paths raise the same stable domain error.
        """
        maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        s1 = maker()
        try:
            await SqlAlchemyProductRepository(s1).save(
                Product(
                    id="prod_race",
                    name="A",
                    price=Decimal("1.00"),
                    currency="USD",
                    created_at=now,
                    updated_at=now,
                )
            )
            s2 = maker()
            try:
                use_case = CreateProduct(
                    SqlAlchemyProductRepository(s2),
                    SqlAlchemyInventoryRepository(s2),
                )
                task = asyncio.create_task(
                    use_case.execute(
                        product_id="prod_race",
                        name="B",
                        price=Decimal("2.00"),
                        currency="USD",
                    )
                )
                await asyncio.sleep(0.5)
                await s1.commit()
                with pytest.raises(ProductAlreadyExistsError):
                    await task
            finally:
                await s2.rollback()
                await s2.close()
        finally:
            await s1.close()
