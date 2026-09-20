"""Inventory API routes."""

from collections.abc import AsyncGenerator

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.api.dependencies import require_roles
from app.modules.iam.application.tokens import CurrentUser
from app.modules.inventory.api.container import (
    InventoryContainer,
    inventory_container,
)
from app.modules.inventory.application.adjust_stock import AdjustStock
from app.modules.inventory.domain.errors import (
    InsufficientStockError,
    InventoryNotFoundError,
)
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/inventory", tags=["inventory"])

OPERATOR_ROLE = "operator"


class StockAdjustRequest(BaseModel):
    delta: int = Field(description="Signed stock delta applied to available stock")


class StockAdjustResponse(BaseModel):
    product_id: str
    available_quantity: int
    reserved_quantity: int


async def _inventory_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the global container's session provider."""
    inventory_container.session.override(session)
    try:
        yield session
    finally:
        inventory_container.session.reset_override()


@router.get("/_health")
def inventory_healthcheck() -> dict[str, str]:
    return {"module": "inventory", "status": "ok", "version": "v1"}


@router.post("/{product_id}/adjust", status_code=200)
@inject
async def adjust_stock(
    product_id: str,
    body: StockAdjustRequest,
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    session: AsyncSession = Depends(_inventory_db_session),
    use_case: AdjustStock = Depends(Provide[InventoryContainer.adjust_stock]),
) -> StockAdjustResponse:
    """Apply an operator-signed stock delta (U1 catalog-cart seeding flow)."""
    del current
    try:
        inventory = await use_case.execute(product_id=product_id, delta=body.delta)
    except InventoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientStockError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return StockAdjustResponse(
        product_id=inventory.product_id,
        available_quantity=inventory.available_quantity,
        reserved_quantity=inventory.reserved_quantity,
    )
