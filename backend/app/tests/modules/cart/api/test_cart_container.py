"""Container wiring tests for the cart module (U2)."""

from typing import cast

import pytest
from dependency_injector import errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.api.container import cart_container
from app.modules.cart.application.add_item import AddCartItem
from app.modules.cart.application.get_cart import GetCart
from app.modules.cart.application.remove_item import RemoveCartItem
from app.modules.cart.application.set_item_quantity import SetCartItemQuantity
from app.modules.cart.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCartRepository,
)
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)


class _FakeSession(AsyncSession):
    def __init__(self) -> None:
        pass


def test_cart_container_requires_a_request_session_override() -> None:
    with pytest.raises(errors.Error):
        cart_container.get_cart()
    with pytest.raises(errors.Error):
        cart_container.add_item()


def test_cart_container_wires_use_cases_to_the_request_session() -> None:
    session = _FakeSession()
    cart_container.session.override(session)
    try:
        get = cart_container.get_cart()
        add = cart_container.add_item()
        setter = cart_container.set_quantity()
        remove = cart_container.remove_item()
    finally:
        cart_container.session.reset_override()

    assert isinstance(get, GetCart)
    assert isinstance(add, AddCartItem)
    assert isinstance(setter, SetCartItemQuantity)
    assert isinstance(remove, RemoveCartItem)
    for use_case in (get, add, setter, remove):
        assert (
            cast(SqlAlchemyCartRepository, use_case._carts)._session  # type: ignore[attr-defined]
            is session
        )
        assert (
            cast(SqlAlchemyProductRepository, use_case._products)._session  # type: ignore[attr-defined]
            is session
        )
