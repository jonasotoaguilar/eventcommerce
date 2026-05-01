"""SQLAlchemy implementation of InventoryRepository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.domain.entities.inventory import Inventory
from app.modules.inventory.domain.repositories.repository import InventoryRepository


class SqlAlchemyInventoryRepository(InventoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_product(self, product_id: str) -> Inventory | None:
        return None

    async def save(self, inventory: Inventory) -> None:
        pass
