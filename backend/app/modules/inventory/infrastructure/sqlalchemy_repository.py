"""SQLAlchemy implementation of InventoryRepository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.repository import InventoryRepository
from app.modules.inventory.infrastructure.models import InventoryModel


class SqlAlchemyInventoryRepository(InventoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_product(self, product_id: str) -> Inventory | None:
        result = await self._session.execute(
            select(InventoryModel).where(InventoryModel.product_id == product_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return Inventory(
            product_id=orm.product_id,
            available_quantity=orm.available_quantity,
            reserved_quantity=orm.reserved_quantity,
        )

    async def save(self, inventory: Inventory) -> None:
        existing = await self.get_by_product(inventory.product_id)
        if existing is not None:
            result = await self._session.execute(
                select(InventoryModel).where(
                    InventoryModel.product_id == inventory.product_id
                )
            )
            orm = result.scalar_one()
            orm.available_quantity = inventory.available_quantity
            orm.reserved_quantity = inventory.reserved_quantity
        else:
            orm = InventoryModel(
                product_id=inventory.product_id,
                available_quantity=inventory.available_quantity,
                reserved_quantity=inventory.reserved_quantity,
            )
            self._session.add(orm)
        await self._session.flush()

    async def lock_and_check_availability(
        self, items: list[tuple[str, int]]
    ) -> list[Inventory]:
        """Lock inventory rows FOR UPDATE and check availability for every line.

        All requested rows are locked in ascending ``product_id`` order
        (deadlock-safe ordering for concurrent multi-line reservations) and
        every line is checked against available stock before anything is
        returned; missing products and insufficient stock raise
        :class:`InsufficientStockError` with no partial reservation. The
        caller applies the actual reservation mutations under the held locks.
        Returns the locked Inventory entities sorted by ``product_id``.
        """
        if not items:
            return []
        items = sorted(items, key=lambda item: item[0])
        product_ids = [product_id for product_id, _ in items]
        result = await self._session.execute(
            select(InventoryModel)
            .where(InventoryModel.product_id.in_(product_ids))
            .order_by(InventoryModel.product_id)
            .with_for_update()
        )
        orms = result.scalars().all()
        by_product = {orm.product_id: orm for orm in orms}
        inventory_list: list[Inventory] = []
        for product_id, quantity in items:
            orm = by_product.get(product_id)
            if orm is None:
                raise InsufficientStockError(f"Product {product_id} not found")
            if orm.available_quantity < quantity:
                raise InsufficientStockError("Not enough stock available")
            inventory_list.append(
                Inventory(
                    product_id=orm.product_id,
                    available_quantity=orm.available_quantity,
                    reserved_quantity=orm.reserved_quantity,
                )
            )
        return inventory_list
