"""CreateProduct use case.

Seeds inventory at zero through the inventory repository boundary so every
catalog product is reservable without a separate provisioning step. The
seed is a no-op when an inventory row already exists for the product.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import ProductAlreadyExistsError
from app.modules.catalog.domain.repository import ProductRepository
from app.modules.catalog.domain.services import touch, validate_product
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.repository import InventoryRepository


class CreateProduct:
    def __init__(
        self,
        repository: ProductRepository,
        inventory_repository: InventoryRepository,
    ) -> None:
        self._repository = repository
        self._inventory = inventory_repository

    async def execute(
        self,
        product_id: str,
        name: str,
        price: Decimal,
        currency: str,
        description: str | None = None,
        active: bool = True,
    ) -> Product:
        existing = await self._repository.get_by_id(product_id)
        if existing is not None:
            raise ProductAlreadyExistsError(f"Product {product_id} already exists")
        now = datetime.now(timezone.utc)
        product = Product(
            id=product_id,
            name=name,
            description=description,
            price=price,
            currency=currency,
            active=active,
            created_at=now,
            updated_at=now,
        )
        validate_product(product)
        touch(product)
        await self._repository.save(product)
        if await self._inventory.get_by_product(product_id) is None:
            await self._inventory.save(
                Inventory(
                    product_id=product_id,
                    available_quantity=0,
                    reserved_quantity=0,
                )
            )
        return product
