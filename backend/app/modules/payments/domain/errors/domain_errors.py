"""Payments domain errors."""

class PaymentsDomainError(Exception):
    """Base error for payments domain."""


class PaymentRejectedError(PaymentsDomainError):
    """Raised when a payment is rejected."""

