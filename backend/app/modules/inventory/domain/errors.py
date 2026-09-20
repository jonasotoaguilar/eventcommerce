"""Inventory domain errors."""


class InventoryDomainError(Exception):
    """Base error for inventory domain."""


class InsufficientStockError(InventoryDomainError):
    """Raised when there is not enough stock."""


class InventoryNotFoundError(InventoryDomainError):
    """Raised when no inventory row exists for a product."""
