"""GetProduct use case (public detail of active products)."""

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import ProductNotFoundError
from app.modules.catalog.domain.repository import ProductRepository


class GetProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(self, product_id: str, *, active_only: bool = True) -> Product:
        product = await self._repository.get_by_id(product_id)
        if product is None or (active_only and not product.active):
            raise ProductNotFoundError(f"Product {product_id} not found")
        return product
