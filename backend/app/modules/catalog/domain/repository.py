"""Catalog repository protocol."""

from typing import Protocol

from app.modules.catalog.domain.entities import Product


class ProductRepository(Protocol):
    async def get_by_id(self, product_id: str) -> Product | None: ...
    async def list_active(self, limit: int = 100, offset: int = 0) -> list[Product]: ...
    async def save(self, product: Product) -> None: ...
