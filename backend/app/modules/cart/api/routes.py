"""Cart API routes (U2 catalog-cart).

One active cart per authenticated shopper, keyed by JWT subject: every
route requires a valid bearer token and scopes reads/writes to it —
request bodies never carry a customer id. ``GET`` lazily creates an
empty cart; ``POST`` increments an existing line; ``PATCH`` sets an
absolute quantity (404 when the line is missing); ``DELETE`` removes a
line idempotently (always 200). Missing and inactive products share one
stable 404 so existence never leaks. Error envelopes stay
``{"detail": ...}`` like the other modules.
"""

from collections.abc import AsyncGenerator

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.api.container import CartContainer, cart_container
from app.modules.cart.api.schemas import (
    AddCartItemRequest,
    CartLineResponse,
    CartResponse,
    SetCartItemQuantityRequest,
)
from app.modules.cart.application.add_item import AddCartItem
from app.modules.cart.application.cart_view import CartView
from app.modules.cart.application.get_cart import GetCart
from app.modules.cart.application.remove_item import RemoveCartItem
from app.modules.cart.application.set_item_quantity import SetCartItemQuantity
from app.modules.cart.domain.errors import (
    CartItemNotFoundError,
    CartLimitExceededError,
    CurrencyMismatchError,
    InvalidQuantityError,
    ProductNotFoundError,
)
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/cart", tags=["cart"])


def _to_response(view: CartView) -> CartResponse:
    return CartResponse(
        cart_id=view.cart_id,
        customer_id=view.customer_id,
        items=[
            CartLineResponse(
                product_id=item.product_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                currency=item.currency,
                line_total=item.line_total,
            )
            for item in view.items
        ],
        subtotal=view.subtotal,
        currency=view.currency,
    )


async def _cart_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the global container's session provider."""
    cart_container.session.override(session)
    try:
        yield session
    finally:
        cart_container.session.reset_override()


@router.get("")
@inject
async def get_cart(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_cart_db_session),
    use_case: GetCart = Depends(Provide[CartContainer.get_cart]),
) -> CartResponse:
    view = await use_case.execute(current.user_id)
    await session.commit()
    return _to_response(view)


@router.post("/items")
@inject
async def add_cart_item(
    body: AddCartItemRequest,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_cart_db_session),
    use_case: AddCartItem = Depends(Provide[CartContainer.add_item]),
) -> CartResponse:
    try:
        view = await use_case.execute(current.user_id, body.product_id, body.quantity)
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except InvalidQuantityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (CartLimitExceededError, CurrencyMismatchError) as exc:
        # A conflicting write may leave the transaction aborted; roll
        # back so the request session stays usable before the 409.
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_response(view)


@router.patch("/items/{product_id}")
@inject
async def set_cart_item_quantity(
    product_id: str,
    body: SetCartItemQuantityRequest,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_cart_db_session),
    use_case: SetCartItemQuantity = Depends(Provide[CartContainer.set_quantity]),
) -> CartResponse:
    try:
        view = await use_case.execute(current.user_id, product_id, body.quantity)
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found") from None
    except CartItemNotFoundError:
        raise HTTPException(status_code=404, detail="Cart item not found") from None
    except InvalidQuantityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CartLimitExceededError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_response(view)


@router.delete("/items/{product_id}")
@inject
async def remove_cart_item(
    product_id: str,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(_cart_db_session),
    use_case: RemoveCartItem = Depends(Provide[CartContainer.remove_item]),
) -> CartResponse:
    view = await use_case.execute(current.user_id, product_id)
    await session.commit()
    return _to_response(view)
