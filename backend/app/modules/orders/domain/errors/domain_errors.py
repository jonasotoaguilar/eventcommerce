"""Orders domain errors."""

class OrdersDomainError(Exception):
    """Base error for orders domain."""


class OrderNotFoundError(OrdersDomainError):
    """Raised when an order cannot be found."""


class InvalidStateTransitionError(OrdersDomainError):
    """Raised when an invalid state transition is attempted."""

