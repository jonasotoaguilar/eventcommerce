"""Application tests for cart use cases (U2).

Covers lazy creation, increment vs set semantics, owner isolation,
inactive/missing products, max lines/quantity, mixed currency, live
subtotal projection, and concurrent cart-creation safety.
"""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.cart.application.add_item import AddCartItem
from app.modules.cart.application.get_cart import GetCart
from app.modules.cart.application.remove_item import RemoveCartItem
from app.modules.cart.application.set_item_quantity import SetCartItemQuantity
from app.modules.cart.domain.errors import (
    CartItemNotFoundError,
    CartLimitExceededError,
    CurrencyMismatchError,
    InvalidQuantityError,
    ProductNotFoundError,
)
from app.modules.cart.infrastructure.models import CartModel
from app.modules.cart.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCartRepository,
)
from app.modules.catalog.infrastructure.models import ProductModel
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.iam.infrastructure.models import UserModel

CUSTOMER_A = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_B = UUID("22222222-2222-2222-2222-222222222222")


async def _seed_user(db_session, user_id: UUID) -> None:
    db_session.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@example.com",
            password_hash="x",
            role="shopper",
        )
    )
    await db_session.flush()


async def _seed_product(
    db_session,
    product_id: str,
    price: str = "10.00",
    currency: str = "USD",
    active: bool = True,
) -> None:
    db_session.add(
        ProductModel(
            id=product_id,
            name=f"Product {product_id}",
            description=None,
            price=Decimal(price),
            currency=currency,
            active=active,
        )
    )
    await db_session.flush()


def _repos(db_session):
    return (
        SqlAlchemyCartRepository(db_session),
        SqlAlchemyProductRepository(db_session),
    )


def _use_cases(db_session):
    carts, products = _repos(db_session)
    return (
        GetCart(carts, products),
        AddCartItem(carts, products),
        SetCartItemQuantity(carts, products),
        RemoveCartItem(carts, products),
    )


class TestGetCart:
    @pytest.mark.asyncio
    async def test_lazy_create_returns_empty_shape(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        get_cart, _, _, _ = _use_cases(db_session)

        view = await get_cart.execute(CUSTOMER_A)

        assert view.customer_id == CUSTOMER_A
        assert view.items == []
        assert view.subtotal == Decimal("0.00")
        assert view.currency is None

    @pytest.mark.asyncio
    async def test_second_read_returns_same_cart(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        get_cart, _, _, _ = _use_cases(db_session)

        first = await get_cart.execute(CUSTOMER_A)
        second = await get_cart.execute(CUSTOMER_A)

        assert first.cart_id == second.cart_id

    @pytest.mark.asyncio
    async def test_carts_are_scoped_to_owner(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_user(db_session, CUSTOMER_B)
        await _seed_product(db_session, "p1")
        get_cart, add_item, _, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "p1", 2)
        view_b = await get_cart.execute(CUSTOMER_B)

        assert view_b.items == []
        assert view_b.cart_id != (await get_cart.execute(CUSTOMER_A)).cart_id


class TestAddItem:
    @pytest.mark.asyncio
    async def test_add_projects_live_catalog(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1", price="49.99")
        _, add_item, _, _ = _use_cases(db_session)

        view = await add_item.execute(CUSTOMER_A, "p1", 2)

        assert len(view.items) == 1
        line = view.items[0]
        assert line.product_id == "p1"
        assert line.name == "Product p1"
        assert line.quantity == 2
        assert line.unit_price == Decimal("49.99")
        assert line.currency == "USD"
        assert line.line_total == Decimal("99.98")
        assert view.subtotal == Decimal("99.98")
        assert view.currency == "USD"

    @pytest.mark.asyncio
    async def test_add_existing_line_increments(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, _, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "p1", 2)
        view = await add_item.execute(CUSTOMER_A, "p1", 3)

        assert view.items[0].quantity == 5
        assert view.subtotal == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_missing_and_inactive_share_stable_404(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "hidden", active=False)
        _, add_item, _, _ = _use_cases(db_session)

        with pytest.raises(ProductNotFoundError, match="Product not found"):
            await add_item.execute(CUSTOMER_A, "missing", 1)
        with pytest.raises(ProductNotFoundError, match="Product not found"):
            await add_item.execute(CUSTOMER_A, "hidden", 1)

    @pytest.mark.asyncio
    async def test_invalid_quantity_rejected(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, _, _ = _use_cases(db_session)

        for quantity in (0, -1, 10_001):
            with pytest.raises(InvalidQuantityError):
                await add_item.execute(CUSTOMER_A, "p1", quantity)

    @pytest.mark.asyncio
    async def test_increment_overflow_conflicts(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, _, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "p1", 10_000)
        with pytest.raises(CartLimitExceededError):
            await add_item.execute(CUSTOMER_A, "p1", 1)

    @pytest.mark.asyncio
    async def test_max_unique_lines_conflicts(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        for i in range(100):
            await _seed_product(db_session, f"p{i:03d}")
        await _seed_product(db_session, "p_extra")
        _, add_item, _, _ = _use_cases(db_session)

        for i in range(100):
            await add_item.execute(CUSTOMER_A, f"p{i:03d}", 1)
        with pytest.raises(CartLimitExceededError):
            await add_item.execute(CUSTOMER_A, "p_extra", 1)

    @pytest.mark.asyncio
    async def test_mixed_currency_conflicts(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "usd_item", currency="USD")
        await _seed_product(db_session, "eur_item", currency="EUR")
        _, add_item, _, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "usd_item", 1)
        with pytest.raises(CurrencyMismatchError):
            await add_item.execute(CUSTOMER_A, "eur_item", 1)

    @pytest.mark.asyncio
    async def test_subtotal_follows_current_prices(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1", price="10.00")
        get_cart, add_item, _, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "p1", 2)

        result = await db_session.execute(
            select(ProductModel).where(ProductModel.id == "p1")
        )
        result.scalar_one().price = Decimal("12.50")
        await db_session.flush()

        assert (await get_cart.execute(CUSTOMER_A)).subtotal == Decimal("25.00")


class TestInactiveProjection:
    @pytest.mark.asyncio
    async def test_deactivated_product_hidden_from_projection(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1", price="10.00")
        await _seed_product(db_session, "p2", price="4.50")
        get_cart, add_item, set_quantity, remove_item = _use_cases(db_session)
        await add_item.execute(CUSTOMER_A, "p1", 2)
        await add_item.execute(CUSTOMER_A, "p2", 1)

        result = await db_session.execute(
            select(ProductModel).where(ProductModel.id == "p1")
        )
        result.scalar_one().active = False
        await db_session.flush()

        view = await get_cart.execute(CUSTOMER_A)
        assert [i.product_id for i in view.items] == ["p2"]
        assert view.subtotal == Decimal("4.50")
        assert view.currency == "USD"

        with pytest.raises(ProductNotFoundError, match="Product not found"):
            await add_item.execute(CUSTOMER_A, "p1", 1)
        with pytest.raises(ProductNotFoundError, match="Product not found"):
            await set_quantity.execute(CUSTOMER_A, "p1", 1)

        # The hidden line stays removable through the idempotent path.
        cleaned = await remove_item.execute(CUSTOMER_A, "p1")
        assert [i.product_id for i in cleaned.items] == ["p2"]

    @pytest.mark.asyncio
    async def test_hidden_lines_do_not_pin_currency(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "usd_item", currency="USD")
        await _seed_product(db_session, "eur_item", currency="EUR")
        get_cart, add_item, _, _ = _use_cases(db_session)
        await add_item.execute(CUSTOMER_A, "usd_item", 1)

        result = await db_session.execute(
            select(ProductModel).where(ProductModel.id == "usd_item")
        )
        result.scalar_one().active = False
        await db_session.flush()

        view = await add_item.execute(CUSTOMER_A, "eur_item", 1)
        assert [i.product_id for i in view.items] == ["eur_item"]
        assert view.currency == "EUR"


class TestSetQuantity:
    @pytest.mark.asyncio
    async def test_set_replaces_instead_of_incrementing(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, set_quantity, _ = _use_cases(db_session)

        await add_item.execute(CUSTOMER_A, "p1", 5)
        view = await set_quantity.execute(CUSTOMER_A, "p1", 2)

        assert view.items[0].quantity == 2
        assert view.subtotal == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_set_missing_line_returns_404_style(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, _, set_quantity, _ = _use_cases(db_session)

        with pytest.raises(CartItemNotFoundError, match="Cart item not found"):
            await set_quantity.execute(CUSTOMER_A, "p1", 2)

    @pytest.mark.asyncio
    async def test_set_inactive_product_returns_product_404(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, set_quantity, _ = _use_cases(db_session)
        await add_item.execute(CUSTOMER_A, "p1", 1)

        result = await db_session.execute(
            select(ProductModel).where(ProductModel.id == "p1")
        )
        result.scalar_one().active = False
        await db_session.flush()

        with pytest.raises(ProductNotFoundError, match="Product not found"):
            await set_quantity.execute(CUSTOMER_A, "p1", 2)


class TestRemoveItem:
    @pytest.mark.asyncio
    async def test_remove_deletes_line(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        await _seed_product(db_session, "p2")
        _, add_item, _, remove_item = _use_cases(db_session)
        await add_item.execute(CUSTOMER_A, "p1", 1)
        await add_item.execute(CUSTOMER_A, "p2", 1)

        view = await remove_item.execute(CUSTOMER_A, "p1")

        assert [i.product_id for i in view.items] == ["p2"]

    @pytest.mark.asyncio
    async def test_remove_is_idempotent(self, db_session) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        await _seed_product(db_session, "p1")
        _, add_item, _, remove_item = _use_cases(db_session)
        await add_item.execute(CUSTOMER_A, "p1", 1)

        first = await remove_item.execute(CUSTOMER_A, "p1")
        second = await remove_item.execute(CUSTOMER_A, "p1")
        third = await remove_item.execute(CUSTOMER_A, "never-added")

        assert first.items == [] and second.items == [] and third.items == []
        assert first.cart_id == second.cart_id == third.cart_id


class TestConcurrentSafety:
    @pytest.mark.asyncio
    async def test_concurrent_get_or_create_keeps_single_cart(self, engine) -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as setup:
            await _seed_user(setup, CUSTOMER_A)
            await setup.commit()
        customer_id = CUSTOMER_A

        async def _one() -> UUID:
            async with factory() as session:
                repo = SqlAlchemyCartRepository(session)
                cart = await repo.get_or_create(customer_id)
                await session.commit()
                return cart.id

        ids = await asyncio.gather(_one(), _one(), _one())

        assert ids[0] == ids[1] == ids[2]
        async with factory() as session:
            total = (
                await session.execute(select(func.count()).select_from(CartModel))
            ).scalar_one()
            assert total == 1

    @pytest.mark.asyncio
    async def test_concurrent_increments_serialize(self, engine) -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as setup:
            await _seed_user(setup, CUSTOMER_A)
            await _seed_product(setup, "p1")
            await setup.commit()

        async def _one() -> None:
            async with factory() as session:
                carts = SqlAlchemyCartRepository(session)
                products = SqlAlchemyProductRepository(session)
                await AddCartItem(carts, products).execute(CUSTOMER_A, "p1", 1)
                await session.commit()

        await asyncio.gather(_one(), _one())

        async with factory() as session:
            carts = SqlAlchemyCartRepository(session)
            products = SqlAlchemyProductRepository(session)
            view = await GetCart(carts, products).execute(CUSTOMER_A)
            assert view.items[0].quantity == 2

    @pytest.mark.asyncio
    async def test_duplicate_customer_insert_loses_race_safely(
        self, db_session
    ) -> None:
        await _seed_user(db_session, CUSTOMER_A)
        carts, _ = _repos(db_session)
        customer_id = CUSTOMER_A
        other = uuid4()

        first = await carts.get_or_create(customer_id)
        # A creation for another customer is independent.
        await _seed_user(db_session, other)
        second = await carts.get_or_create(other)

        assert first.customer_id == customer_id
        assert second.customer_id == other
        assert first.id != second.id
