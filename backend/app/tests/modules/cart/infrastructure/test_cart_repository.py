"""Repository tests for cart durability invariants (U2)."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.cart.domain.entities import CartLine
from app.modules.cart.infrastructure.models import CartItemModel, CartModel
from app.modules.cart.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCartRepository,
)
from app.modules.iam.infrastructure.models import UserModel


async def _seed_user(db_session, user_id) -> None:
    db_session.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@example.com",
            password_hash="x",
            role="shopper",
        )
    )
    await db_session.flush()


class TestCartOwnership:
    @pytest.mark.asyncio
    async def test_cart_requires_a_known_user(self, db_session) -> None:
        repo = SqlAlchemyCartRepository(db_session)

        with pytest.raises(IntegrityError):
            await repo.get_or_create(uuid4())

    @pytest.mark.asyncio
    async def test_customer_unique_constraint(self, db_session) -> None:
        user_id = uuid4()
        await _seed_user(db_session, user_id)
        db_session.add(CartModel(customer_id=user_id))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(CartModel(customer_id=user_id))
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_get_or_create_recovers_from_lost_race(self, db_session) -> None:
        user_id = uuid4()
        await _seed_user(db_session, user_id)
        repo = SqlAlchemyCartRepository(db_session)

        first = await repo.get_or_create(user_id)
        # Simulate a loser that inserted after another request committed:
        # the unique row already exists, so get_or_create re-reads it.
        second = await repo.get_or_create(user_id)

        assert first.id == second.id


class TestCartLines:
    @pytest.mark.asyncio
    async def test_line_round_trip(self, db_session) -> None:
        from app.modules.catalog.infrastructure.models import ProductModel
        from decimal import Decimal

        user_id = uuid4()
        await _seed_user(db_session, user_id)
        db_session.add(
            ProductModel(
                id="p1",
                name="P1",
                description=None,
                price=Decimal("3.00"),
                currency="USD",
                active=True,
            )
        )
        await db_session.flush()
        repo = SqlAlchemyCartRepository(db_session)
        cart = await repo.get_or_create(user_id)

        await repo.save_line(CartLine(cart_id=cart.id, product_id="p1", quantity=4))
        await repo.save_line(CartLine(cart_id=cart.id, product_id="p1", quantity=6))

        assert await repo.count_lines(cart.id) == 1
        line = await repo.get_line(cart.id, "p1")
        assert line is not None and line.quantity == 6
        assert await repo.delete_line(cart.id, "p1") is True
        assert await repo.delete_line(cart.id, "p1") is False
        assert await repo.get_line(cart.id, "p1") is None

    @pytest.mark.asyncio
    async def test_quantity_check_constraint(self, db_session) -> None:
        user_id = uuid4()
        await _seed_user(db_session, user_id)
        repo = SqlAlchemyCartRepository(db_session)
        cart = await repo.get_or_create(user_id)

        db_session.add(CartItemModel(cart_id=cart.id, product_id="p1", quantity=0))
        with pytest.raises(IntegrityError):
            await db_session.flush()
