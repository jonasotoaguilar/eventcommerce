"""Domain tests for cart invariants and live projections (U2)."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.cart.application.cart_view import build_cart_view
from app.modules.cart.domain.entities import Cart, CartLine
from app.modules.cart.domain.errors import InvalidQuantityError
from app.modules.cart.domain.services import (
    MAX_LINES,
    MAX_QUANTITY,
    validate_quantity,
)
from app.modules.catalog.domain.entities import Product


def _cart() -> Cart:
    return Cart(id=uuid4(), customer_id=uuid4())


def _product(product_id: str, price: str, currency: str = "USD") -> Product:
    return Product(
        id=product_id,
        name=f"Product {product_id}",
        price=Decimal(price),
        currency=currency,
    )


class TestValidateQuantity:
    @pytest.mark.parametrize("quantity", [1, 2, 10_000])
    def test_bounds_are_accepted(self, quantity: int) -> None:
        assert validate_quantity(quantity) == quantity

    @pytest.mark.parametrize("quantity", [0, -1, 10_001, 1_000_000])
    def test_out_of_range_rejected(self, quantity: int) -> None:
        with pytest.raises(InvalidQuantityError):
            validate_quantity(quantity)

    def test_non_integers_rejected(self) -> None:
        for quantity in ("2", 2.0, None, True):
            with pytest.raises(InvalidQuantityError):
                validate_quantity(quantity)  # type: ignore[arg-type]

    def test_limits_match_checkout_contract(self) -> None:
        assert MAX_QUANTITY == 10_000
        assert MAX_LINES == 100


class TestBuildCartView:
    def test_empty_cart_shape(self) -> None:
        cart = _cart()

        view = build_cart_view(cart, [], {})

        assert view.cart_id == cart.id
        assert view.customer_id == cart.customer_id
        assert view.items == []
        assert view.subtotal == Decimal("0.00")
        assert view.currency is None

    def test_line_total_and_subtotal_come_from_live_prices(self) -> None:
        cart = _cart()
        lines = [
            CartLine(cart_id=cart.id, product_id="p1", quantity=2),
            CartLine(cart_id=cart.id, product_id="p2", quantity=3),
        ]
        products = {
            "p1": _product("p1", "10.00"),
            "p2": _product("p2", "4.50"),
        }

        view = build_cart_view(cart, lines, products)

        assert [i.line_total for i in view.items] == [
            Decimal("20.00"),
            Decimal("13.50"),
        ]
        assert view.subtotal == Decimal("33.50")
        assert view.currency == "USD"
        assert view.items[0].unit_price == Decimal("10.00")
        assert view.items[0].name == "Product p1"

    def test_price_change_is_reflected_without_touching_lines(self) -> None:
        cart = _cart()
        lines = [CartLine(cart_id=cart.id, product_id="p1", quantity=2)]

        before = build_cart_view(cart, lines, {"p1": _product("p1", "10.00")})
        after = build_cart_view(cart, lines, {"p1": _product("p1", "12.50")})

        assert before.subtotal == Decimal("20.00")
        assert after.subtotal == Decimal("25.00")

    def test_stale_lines_are_skipped(self) -> None:
        cart = _cart()
        lines = [
            CartLine(cart_id=cart.id, product_id="p1", quantity=1),
            CartLine(cart_id=cart.id, product_id="ghost", quantity=9),
        ]

        view = build_cart_view(cart, lines, {"p1": _product("p1", "5.00")})

        assert [i.product_id for i in view.items] == ["p1"]
        assert view.subtotal == Decimal("5.00")

    def test_inactive_lines_are_hidden_and_excluded_from_subtotal(self) -> None:
        cart = _cart()
        lines = [
            CartLine(cart_id=cart.id, product_id="p1", quantity=2),
            CartLine(cart_id=cart.id, product_id="p2", quantity=1),
        ]
        dormant = _product("p1", "10.00")
        dormant.active = False
        products = {"p1": dormant, "p2": _product("p2", "4.50")}

        view = build_cart_view(cart, lines, products)

        assert [i.product_id for i in view.items] == ["p2"]
        assert view.subtotal == Decimal("4.50")
        assert view.currency == "USD"

    def test_fully_hidden_cart_looks_empty(self) -> None:
        cart = _cart()
        lines = [CartLine(cart_id=cart.id, product_id="p1", quantity=2)]
        dormant = _product("p1", "10.00")
        dormant.active = False

        view = build_cart_view(cart, lines, {"p1": dormant})

        assert view.items == []
        assert view.subtotal == Decimal("0.00")
        assert view.currency is None
