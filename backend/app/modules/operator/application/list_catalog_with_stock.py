"""ListCatalogWithStock use case (operator catalog read model).

Lists every product including inactive ones ordered by product id, and
joins stock from the inventory context without adding a dependency
between the catalog and inventory modules. A product without an
inventory row keeps null quantities rather than a fabricated zero.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.modules.catalog.domain.repository import ProductRepository
from app.modules.inventory.domain.repository import InventoryRepository


@dataclass(frozen=True)
class CatalogRow:
    product_id: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    active: bool
    available_quantity: int | None
    reserved_quantity: int | None


class ListCatalogWithStock:
    def __init__(
        self,
        product_repository: ProductRepository,
        inventory_repository: InventoryRepository,
    ) -> None:
        self._products = product_repository
        self._inventory = inventory_repository

    async def execute(self, limit: int = 100, offset: int = 0) -> list[CatalogRow]:
        products = await self._products.list_all(limit=limit, offset=offset)
        stock = await self._inventory.list_by_product_ids([p.id for p in products])
        by_product = {row.product_id: row for row in stock}
        rows = []
        for product in products:
            inventory = by_product.get(product.id)
            rows.append(
                CatalogRow(
                    product_id=product.id,
                    name=product.name,
                    description=product.description,
                    price=product.price,
                    currency=product.currency,
                    active=product.active,
                    available_quantity=inventory.available_quantity
                    if inventory is not None
                    else None,
                    reserved_quantity=inventory.reserved_quantity
                    if inventory is not None
                    else None,
                )
            )
        return rows
