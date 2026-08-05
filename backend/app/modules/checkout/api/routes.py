"""Checkout API routes (tasks 3.16, 3.18).

``POST /api/v1/checkout`` maps the orchestration outcome onto HTTP:
201 for a created terminal order, 409 when an ``Idempotency-Key`` is
reused with a different payload, 422 for schema/header validation, and
500 (with a rollback) for unexpected failures. The ``Idempotency-Key``
header is authoritative over any body-sent key: an absent header drops
the body key, a present header replaces it after visible-ASCII
validation. Structured logs at this boundary (``checkout_started``,
``checkout_rolled_back``) carry only the key hash — never the raw key;
the core emits ``checkout_completed/replayed/conflict/
notification_failed``.
"""

import logging
from collections.abc import AsyncGenerator

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.api.container import CheckoutContainer, checkout_container
from app.modules.checkout.api.schemas import CheckoutRequest, VISIBLE_ASCII_PATTERN
from app.modules.checkout.application.checkout import Checkout, CheckoutResult
from app.modules.checkout.application.errors import IdempotencyConflictError
from app.modules.checkout.application.helpers import hash_key
from app.shared.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkout", tags=["checkout"])


async def _checkout_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the container's session provider."""
    checkout_container.session.override(session)
    try:
        yield session
    finally:
        checkout_container.session.reset_override()


def _with_idempotency_header(
    body: CheckoutRequest, header_value: str | None
) -> CheckoutRequest:
    """Map the Idempotency-Key header onto the core request.

    The header is authoritative: a present header replaces any body-sent
    key; an absent header drops the body-sent key entirely.
    """
    if header_value is None:
        return body.model_copy(update={"idempotency_key": None})
    return CheckoutRequest.model_validate(
        {**body.model_dump(), "idempotency_key": header_value}
    )


@router.post("", status_code=201)
@inject
async def create_checkout(
    body: CheckoutRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=VISIBLE_ASCII_PATTERN.pattern,
    ),
    session: AsyncSession = Depends(_checkout_db_session),
    use_case: Checkout = Depends(Provide[CheckoutContainer.checkout]),
) -> JSONResponse:
    request = _with_idempotency_header(body, idempotency_key)
    key = request.idempotency_key
    key_hash = hash_key(key) if key is not None else ""
    logger.info("checkout_started key_hash=%s", key_hash)
    try:
        result: CheckoutResult = await use_case.execute(request)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("checkout_rolled_back key_hash=%s", key_hash)
        await session.rollback()
        raise HTTPException(status_code=500, detail="internal error") from None
    return JSONResponse(content=result.body, status_code=result.status_code)
