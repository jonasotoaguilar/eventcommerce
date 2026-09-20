"""Cart domain errors."""


class CartError(Exception):
    """Base error for the cart bounded context."""


class ProductNotFoundError(CartError):
    """Raised when a product is missing or inactive.

    Missing and inactive products share one stable message so cart
    responses never leak catalog existence beyond a 404.
    """


class CartItemNotFoundError(CartError):
    """Raised when a cart line cannot be found."""


class InvalidQuantityError(CartError):
    """Raised when a quantity violates the 1..10,000 invariant."""


class CartLimitExceededError(CartError):
    """Raised when a cart constraint conflicts (max lines/quantity)."""


class CurrencyMismatchError(CartError):
    """Raised when adding a product with a different cart currency."""
