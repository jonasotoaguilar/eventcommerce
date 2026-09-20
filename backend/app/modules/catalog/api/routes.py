"""Catalog API routes (U1 catalog-cart).

Public browse/detail expose only active products — missing and inactive
are indistinguishable (404) to avoid an existence oracle. Writes require
role ``operator`` and return 409 when the product id already exists.
Error envelopes stay ``{"detail": ...}`` like the other modules.
"""

from collections.abc import AsyncGenerator

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.api.container import CatalogContainer, catalog_container
from app.modules.catalog.api.schemas import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
)
from app.modules.catalog.application.create_product import CreateProduct
from app.modules.catalog.application.get_product import GetProduct
from app.modules.catalog.application.list_products import ListProducts
from app.modules.catalog.application.update_product import UpdateProduct
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import (
    InvalidProductError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from app.modules.iam.api.dependencies import require_roles
from app.modules.iam.application.tokens import CurrentUser
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/catalog", tags=["catalog"])

OPERATOR_ROLE = "operator"


def _to_response(product: Product) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        currency=product.currency,
        active=product.active,
        created_at=product.created_at.isoformat() if product.created_at else None,
        updated_at=product.updated_at.isoformat() if product.updated_at else None,
    )


async def _catalog_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the global container's session provider."""
    catalog_container.session.override(session)
    try:
        yield session
    finally:
        catalog_container.session.reset_override()


@router.get("")
@inject
async def list_products(
    session: AsyncSession = Depends(_catalog_db_session),
    use_case: ListProducts = Depends(Provide[CatalogContainer.list_products]),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ProductResponse]:
    del session
    products = await use_case.execute(limit=limit, offset=offset)
    return [_to_response(p) for p in products]


@router.get("/{product_id}")
@inject
async def get_product(
    product_id: str,
    session: AsyncSession = Depends(_catalog_db_session),
    use_case: GetProduct = Depends(Provide[CatalogContainer.get_product]),
) -> ProductResponse:
    del session
    try:
        product = await use_case.execute(product_id)
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found") from None
    return _to_response(product)


@router.post("", status_code=201)
@inject
async def create_product(
    body: ProductCreateRequest,
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    session: AsyncSession = Depends(_catalog_db_session),
    use_case: CreateProduct = Depends(Provide[CatalogContainer.create_product]),
) -> ProductResponse:
    del current
    try:
        product = await use_case.execute(
            product_id=body.id,
            name=body.name,
            price=body.price,
            currency=body.currency,
            description=body.description,
            active=body.active,
        )
    except ProductAlreadyExistsError as exc:
        # A unique-key race leaves the transaction aborted; roll back so
        # the request session stays usable before reporting the 409.
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidProductError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _to_response(product)


@router.patch("/{product_id}")
@inject
async def update_product(
    product_id: str,
    body: ProductUpdateRequest,
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    session: AsyncSession = Depends(_catalog_db_session),
    use_case: UpdateProduct = Depends(Provide[CatalogContainer.update_product]),
) -> ProductResponse:
    del current
    try:
        product = await use_case.execute(
            product_id=product_id,
            name=body.name,
            description=body.description,
            price=body.price,
            currency=body.currency,
            active=body.active,
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except InvalidProductError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _to_response(product)
