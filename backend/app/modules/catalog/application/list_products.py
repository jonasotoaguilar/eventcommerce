"""ListProducts use case (public browse of active products)."""

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.repository import ProductRepository

MAX_LIMIT = 200


class ListProducts:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, limit: int = 100, offset: int = 0) -> list[Product]:
        limit = max(1, min(limit, MAX_LIMIT))
        offset = max(0, offset)
        return await self._repository.list_active(limit=limit, offset=offset)
