"""SQLAlchemy implementation of CartRepository.

``get_or_create`` serializes concurrent cart creation through the
``uq_carts_customer_id`` constraint: a loser rolls back its poisoned
transaction and re-reads, retrying the insert while the winner is
still uncommitted (the loser's insert then blocks on the unique index
until the winner commits). Line increments serialize on the cart row
via ``SELECT ... FOR UPDATE`` (a no-op on drivers without locking,
where the PK/unique constraints still keep state safe).
"""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.domain.entities import Cart, CartLine
from app.modules.cart.domain.repository import CartRepository
from app.modules.cart.infrastructure.models import CartItemModel, CartModel

_MAX_CREATE_ATTEMPTS = 5


class SqlAlchemyCartRepository(CartRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_customer(self, customer_id: UUID) -> Cart | None:
        result = await self._session.execute(
            select(CartModel).where(CartModel.customer_id == customer_id)
        )
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def get_or_create(self, customer_id: UUID) -> Cart:
        last_conflict: IntegrityError | None = None
        for _ in range(_MAX_CREATE_ATTEMPTS):
            result = await self._session.execute(
                select(CartModel)
                .where(CartModel.customer_id == customer_id)
                .with_for_update()
            )
            orm = result.scalar_one_or_none()
            if orm is not None:
                return self._to_domain(orm)
            pending = CartModel(id=uuid4(), customer_id=customer_id)
            self._session.add(pending)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                # Lost a concurrent creation race (or hit the users FK
                # for an unknown customer): roll back the poisoned
                # transaction and re-read instead of surfacing a 500.
                await self._session.rollback()
                last_conflict = exc
                continue
            return self._to_domain(pending)
        assert last_conflict is not None  # noqa: S101
        raise last_conflict

    async def list_lines(self, cart_id: UUID) -> list[CartLine]:
        result = await self._session.execute(
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
            .order_by(CartItemModel.product_id)
        )
        return [
            CartLine(
                cart_id=orm.cart_id,
                product_id=orm.product_id,
                quantity=orm.quantity,
            )
            for orm in result.scalars().all()
        ]

    async def get_line(self, cart_id: UUID, product_id: str) -> CartLine | None:
        result = await self._session.execute(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart_id,
                CartItemModel.product_id == product_id,
            )
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return CartLine(
            cart_id=orm.cart_id, product_id=orm.product_id, quantity=orm.quantity
        )

    async def count_lines(self, cart_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
        )
        return int(result.scalar_one())

    async def save_line(self, line: CartLine) -> None:
        result = await self._session.execute(
            select(CartItemModel).where(
                CartItemModel.cart_id == line.cart_id,
                CartItemModel.product_id == line.product_id,
            )
        )
        orm = result.scalar_one_or_none()
        if orm is not None:
            orm.quantity = line.quantity
        else:
            self._session.add(
                CartItemModel(
                    cart_id=line.cart_id,
                    product_id=line.product_id,
                    quantity=line.quantity,
                )
            )
        await self._session.flush()

    async def delete_line(self, cart_id: UUID, product_id: str) -> bool:
        result = await self._session.execute(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart_id,
                CartItemModel.product_id == product_id,
            )
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    def _to_domain(self, orm: CartModel) -> Cart:
        return Cart(
            id=orm.id,
            customer_id=orm.customer_id,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
