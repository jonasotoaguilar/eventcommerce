"""SQLAlchemy implementation of ProductRepository."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import ProductAlreadyExistsError
from app.modules.catalog.domain.repository import ProductRepository
from app.modules.catalog.infrastructure.models import ProductModel


def _is_catalog_pk_conflict(exc: IntegrityError) -> bool:
    """Return True only for a ``catalog_products`` primary-key conflict.

    Matches the exact ``catalog_products_pkey`` constraint name, or a
    unique-violation (pgcode 23505) mentioning ``catalog_products``.
    Anything else is re-raised untouched so unrelated integrity errors
    are never swallowed.
    """
    # Inspect only the DBAPI error: str(exc) echoes the SQL statement,
    # which always mentions catalog_products and would cause false matches.
    haystack = str(exc.orig).lower() if exc.orig is not None else ""
    if "catalog_products_pkey" in haystack:
        return True
    pgcode = getattr(exc.orig, "pgcode", None)
    return pgcode == "23505" and "catalog_products" in haystack


class SqlAlchemyProductRepository(ProductRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: str) -> Product | None:
        result = await self._session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[Product]:
        result = await self._session.execute(
            select(ProductModel)
            .where(ProductModel.active.is_(True))
            .order_by(ProductModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(orm) for orm in result.scalars().all()]

    async def save(self, product: Product) -> None:
        result = await self._session.execute(
            select(ProductModel).where(ProductModel.id == product.id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.name = product.name
            existing.description = product.description
            existing.price = product.price
            existing.currency = product.currency
            existing.active = product.active
            existing.updated_at = product.updated_at
        else:
            self._session.add(
                ProductModel(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    price=product.price,
                    currency=product.currency,
                    active=product.active,
                    created_at=product.created_at,
                    updated_at=product.updated_at,
                )
            )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent insert may win the check-then-insert race in
            # CreateProduct; map only that PK conflict to a stable domain
            # error so the API stays 409 instead of 500.
            if _is_catalog_pk_conflict(exc):
                raise ProductAlreadyExistsError(
                    f"Product {product.id} already exists"
                ) from exc
            raise

    def _to_domain(self, orm: ProductModel) -> Product:
        return Product(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            price=orm.price,
            currency=orm.currency,
            active=orm.active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
