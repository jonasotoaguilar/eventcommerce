"""Catalog domain errors."""


class CatalogDomainError(Exception):
    """Base error for catalog domain."""


class ProductNotFoundError(CatalogDomainError):
    """Raised when a product cannot be found."""


class ProductAlreadyExistsError(CatalogDomainError):
    """Raised when creating a product whose id already exists."""


class InvalidProductError(CatalogDomainError):
    """Raised when product field values violate domain invariants."""
