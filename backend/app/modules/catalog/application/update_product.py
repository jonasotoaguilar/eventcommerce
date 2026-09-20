"""UpdateProduct use case (operator-only at the API boundary)."""

from decimal import Decimal

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import ProductNotFoundError
from app.modules.catalog.domain.repository import ProductRepository
from app.modules.catalog.domain.services import touch, validate_product


class UpdateProduct:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        price: Decimal | None = None,
        currency: str | None = None,
        active: bool | None = None,
        clear_description: bool = False,
    ) -> Product:
        product = await self._repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} not found")
        if name is not None:
            product.name = name
        if clear_description:
            product.description = None
        elif description is not None:
            product.description = description
        if price is not None:
            product.price = price
        if currency is not None:
            product.currency = currency
        if active is not None:
            product.active = active
        validate_product(product)
        touch(product)
        await self._repository.save(product)
        return product
