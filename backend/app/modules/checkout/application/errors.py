"""Checkout application errors."""


class CheckoutError(Exception):
    """Base error for the checkout orchestrator."""


class IdempotencyConflictError(CheckoutError):
    """Raised when an Idempotency-Key is reused with a different payload."""


class CartNotFoundError(CheckoutError):
    """Raised when a cart id is missing or not owned by the caller.

    Missing and not-owned share one stable message so cart existence
    and ownership never leak beyond a 404.
    """


class EmptyCartError(CheckoutError):
    """Raised when a cart has no checkoutable lines.

    Covers a cart with no stored lines and a cart whose lines are all
    hidden (missing or inactive products): after active-only projection
    nothing remains to charge.
    """


class CartCurrencyMismatchError(CheckoutError):
    """Raised when active cart lines span more than one currency."""


class CartTotalExceededError(CheckoutError):
    """Raised when a cart-derived subtotal exceeds the maximum amount.

    Mirrors the inline ``amount <= MAX_AMOUNT`` schema cap so both
    checkout shapes share one limit; mapped to a stable 422.
    """
