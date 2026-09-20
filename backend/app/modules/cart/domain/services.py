"""Pure domain logic for cart lines."""

from app.modules.cart.domain.errors import InvalidQuantityError

MIN_QUANTITY = 1
MAX_QUANTITY = 10_000
MAX_LINES = 100


def validate_quantity(quantity: int) -> int:
    """Validate the shared 1..10,000 line-quantity invariant."""
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise InvalidQuantityError("Quantity must be between 1 and 10000")
    if quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:
        raise InvalidQuantityError("Quantity must be between 1 and 10000")
    return quantity
