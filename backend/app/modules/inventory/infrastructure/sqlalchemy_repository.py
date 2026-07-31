"""SQLAlchemy implementation of InventoryRepository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.domain.entities import Inventory
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
