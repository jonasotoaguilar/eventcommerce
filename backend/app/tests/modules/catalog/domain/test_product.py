"""Domain validation tests for catalog products (U1)."""

from decimal import Decimal

import pytest

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import InvalidProductError
from app.modules.catalog.domain.services import validate_product


def _product(**overrides) -> Product:
    base: dict = {
        "id": "prod_1",
        "name": "Workshop Ticket",
        "price": Decimal("49.99"),
        "currency": "USD",
    }
    base.update(overrides)
    return Product(**base)


class TestValidateProduct:
    def test_valid_product_passes(self) -> None:
        assert validate_product(_product()).id == "prod_1"

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(id=""))

    def test_overlong_id_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(id="p" * 129))

    def test_boundary_id_128_accepted(self) -> None:
        assert validate_product(_product(id="p" * 128)).id == "p" * 128

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(name="   "))

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(price=Decimal("-0.01")))

    def test_price_above_max_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(price=Decimal("1000000000.00")))

    def test_price_max_boundary_accepted(self) -> None:
        assert validate_product(
            _product(price=Decimal("999999999.99"))
        ).price == Decimal("999999999.99")

    def test_price_with_three_decimals_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(price=Decimal("10.999")))

    def test_non_finite_price_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(price=Decimal("NaN")))
        with pytest.raises(InvalidProductError):
            validate_product(_product(price=Decimal("Infinity")))

    def test_lowercase_currency_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(currency="usd"))

    def test_two_letter_currency_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(currency="US"))

    def test_overlong_description_rejected(self) -> None:
        with pytest.raises(InvalidProductError):
            validate_product(_product(description="d" * 2001))
