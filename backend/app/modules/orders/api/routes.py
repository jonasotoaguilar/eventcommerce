"""Orders API routes (U5: JWT-subject ownership).

Write paths derive ``customer_id`` from the authenticated subject; a
client-sent ``customer_id`` is accepted for compatibility but ignored.
Reads allow only the owning customer or role ``operator`` and return 404
otherwise — missing and forbidden are indistinguishable to avoid an
existence oracle.
"""

from collections.abc import AsyncGenerator
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser

from app.modules.orders.api.container import OrdersContainer, orders_container
from app.modules.orders.api.schemas import (
    OrderCreateRequest,
    OrderResponse,
    TimelineEventResponse,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.application.get_order import GetOrder
from app.modules.orders.application.get_order_timeline import GetOrderTimeline
from app.modules.orders.domain.entities import OrderItem
from app.modules.orders.domain.errors import OrderNotFoundError
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/orders", tags=["orders"])

OPERATOR_ROLE = "operator"


def _ensure_owner_or_operator(order_customer_id: str, current: CurrentUser) -> None:
    """Allow only the owning customer or an operator; else 404 (no oracle)."""
    if order_customer_id != str(current.user_id) and current.role != OPERATOR_ROLE:
        raise HTTPException(status_code=404, detail="Order not found")


async def _orders_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the global container's session provider."""
    orders_container.session.override(session)
    try:
        yield session
    finally:
        orders_container.session.reset_override()


@router.post("", status_code=201)
@inject
async def create_order(
    body: OrderCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_orders_db_session),
    use_case: CreateOrder = Depends(Provide[OrdersContainer.create_order]),
) -> OrderResponse:
    order = await use_case.execute(
        customer_id=str(current.user_id),
        items=[
            OrderItem(product_id=i.product_id, quantity=i.quantity) for i in body.items
        ],
    )
    await session.commit()
    return OrderResponse(order_id=str(order.id), status=order.status)


@router.get("/{order_id}")
@inject
async def get_order(
    order_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_orders_db_session),
    use_case: GetOrder = Depends(Provide[OrdersContainer.get_order]),
) -> dict:
    try:
        order = await use_case.execute(order_id)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found") from None
    _ensure_owner_or_operator(order.customer_id, current)
    return {
        "order_id": str(order.id),
        "customer_id": order.customer_id,
        "status": order.status,
        "cancel_reason": order.cancel_reason,
        "items": [
            {"product_id": i.product_id, "quantity": i.quantity} for i in order.items
        ],
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }


@router.get("/{order_id}/timeline")
@inject
async def get_timeline(
    order_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_orders_db_session),
    use_case: GetOrderTimeline = Depends(Provide[OrdersContainer.get_order_timeline]),
    get_order_use_case: GetOrder = Depends(Provide[OrdersContainer.get_order]),
) -> list[TimelineEventResponse]:
    try:
        order = await get_order_use_case.execute(order_id)
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found") from None
    _ensure_owner_or_operator(order.customer_id, current)
    events = await use_case.execute(order_id)
    return [TimelineEventResponse(**e) for e in events]
