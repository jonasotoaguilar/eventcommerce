"""Operator API routes (read-only order queue, catalog, payment simulation).

All endpoints require JWT role ``operator`` (401 anonymous, 403
otherwise).

``GET /api/v1/operator/orders``: ``status`` accepts only the five
delivered order statuses; ``created_from`` is inclusive and
``created_to`` is exclusive. Money is projected from the latest
payment row per order and stays null when the order has no payment;
``item_count`` is the sum of line quantities.

``GET /api/v1/operator/catalog``: lists inactive products too, with
stock joined from the inventory context and null quantities when the
product has no inventory row.

``GET /api/v1/operator/payments/simulation``: evaluates the delivered
deterministic payment policy for the given inputs without touching
storage.
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.api.schemas import MAX_AMOUNT
from app.modules.payments.domain.policy import (
    APPROVAL_THRESHOLD,
    is_payment_approved,
    payment_digest_byte,
)

from app.modules.iam.api.dependencies import require_roles
from app.modules.iam.application.tokens import CurrentUser
from app.modules.operator.api.container import (
    OperatorContainer,
    operator_container,
)
from app.modules.operator.api.schemas import (
    CatalogRowResponse,
    OrderQueueRowResponse,
    PaymentSimulationResponse,
)
from app.modules.operator.application.list_catalog_with_stock import (
    ListCatalogWithStock,
)
from app.modules.operator.application.list_order_queue import ListOrderQueue
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/operator", tags=["operator"])

OPERATOR_ROLE = "operator"

# Checkout normalizes currency case before validating, so accepting any case
# here keeps this panel's decision identical to the real checkout flow.
_CURRENCY_QUERY_PATTERN = r"^[A-Za-z]{3}$"

OrderQueueStatus = Literal[
    "pending",
    "inventory_reserved",
    "payment_authorized",
    "confirmed",
    "cancelled",
]


async def _operator_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the global container's session provider."""
    operator_container.session.override(session)
    try:
        yield session
    finally:
        operator_container.session.reset_override()


@router.get("/orders")
@inject
async def list_order_queue(
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    session: AsyncSession = Depends(_operator_db_session),
    use_case: ListOrderQueue = Depends(Provide[OperatorContainer.list_order_queue]),
    status: OrderQueueStatus | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OrderQueueRowResponse]:
    del current
    del session
    rows = await use_case.execute(
        status=status,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return [
        OrderQueueRowResponse(
            order_id=row.order_id,
            customer_id=row.customer_id,
            status=row.status,
            created_at=row.created_at,
            cancel_reason=row.cancel_reason,
            item_count=row.item_count,
            total=row.total,
            currency=row.currency,
        )
        for row in rows
    ]


@router.get("/catalog")
@inject
async def list_catalog(
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    session: AsyncSession = Depends(_operator_db_session),
    use_case: ListCatalogWithStock = Depends(
        Provide[OperatorContainer.list_catalog_with_stock]
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CatalogRowResponse]:
    del current
    del session
    rows = await use_case.execute(limit=limit, offset=offset)
    return [
        CatalogRowResponse(
            product_id=row.product_id,
            name=row.name,
            description=row.description,
            price=row.price,
            currency=row.currency,
            active=row.active,
            available_quantity=row.available_quantity,
            reserved_quantity=row.reserved_quantity,
        )
        for row in rows
    ]


@router.get("/payments/simulation")
async def simulate_payment(
    current: CurrentUser = Depends(require_roles(OPERATOR_ROLE)),
    order_id: UUID = Query(),
    amount: Decimal = Query(gt=Decimal("0"), le=MAX_AMOUNT),  # type: ignore[bad-argument-type]
    currency: str = Query(pattern=_CURRENCY_QUERY_PATTERN),
) -> PaymentSimulationResponse:
    del current
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise HTTPException(
            status_code=422, detail="amount must have at most two decimal places"
        )
    normalized_currency = currency.upper()
    return PaymentSimulationResponse(
        order_id=order_id,
        amount=amount,
        currency=normalized_currency,
        approved=is_payment_approved(str(order_id), amount, normalized_currency),
        digest_byte=payment_digest_byte(str(order_id), amount, normalized_currency),
        approval_threshold=APPROVAL_THRESHOLD,
    )
