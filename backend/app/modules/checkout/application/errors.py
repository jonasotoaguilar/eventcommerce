"""Checkout application errors."""


class CheckoutError(Exception):
    """Base error for the checkout orchestrator."""


class IdempotencyConflictError(CheckoutError):
    """Raised when an Idempotency-Key is reused with a different payload."""
