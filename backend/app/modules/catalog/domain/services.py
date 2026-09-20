"""Pure domain logic for catalog products."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.errors import InvalidProductError

MAX_PRODUCT_ID_LENGTH = 128
MAX_PRICE = Decimal("999999999.99")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def validate_product_id(product_id: str) -> str:
    if not product_id or len(product_id) > MAX_PRODUCT_ID_LENGTH:
        raise InvalidProductError(
            f"Product id must be 1..{MAX_PRODUCT_ID_LENGTH} characters"
        )
    return product_id


def validate_name(name: str) -> str:
    if not name or not name.strip() or len(name) > 255:
        raise InvalidProductError("Product name must be 1..255 characters")
    return name


def validate_price(price: Decimal) -> Decimal:
    if not isinstance(price, Decimal):
        try:
            price = Decimal(str(price))
        except Exception as exc:
            raise InvalidProductError("Product price must be a decimal") from exc
    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        raise InvalidProductError("Product price must be in 0..999999999.99")
    exponent = price.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise InvalidProductError("Product price must have at most 2 decimals")
    return price


def validate_currency(currency: str) -> str:
    if not _CURRENCY_PATTERN.match(currency or ""):
        raise InvalidProductError("Currency must be a 3-letter uppercase code")
    return currency


def validate_product(product: Product) -> Product:
    """Validate invariants in place and return the product."""
    validate_product_id(product.id)
    validate_name(product.name)
    product.price = validate_price(product.price)
    validate_currency(product.currency)
    if product.description is not None and len(product.description) > 2000:
        raise InvalidProductError("Product description must be at most 2000 characters")
    return product


def touch(product: Product) -> None:
    """Refresh ``updated_at`` (``created_at`` is set at construction)."""
    product.updated_at = datetime.now(timezone.utc)
