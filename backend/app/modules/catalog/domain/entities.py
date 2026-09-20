"""Catalog domain entities."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


@dataclass
class Product:
    """Sellable catalog product.

    ``id`` is bounded text (1..128 chars) so it stays compatible with the
    existing ``product_id`` columns in orders/inventory. ``price`` is a
    Decimal in ``0..999999999.99`` with at most 2 decimals; ``currency``
    is a 3-letter uppercase ISO code.
    """

    id: str
    name: str
    price: Decimal
    currency: str
    active: bool = True
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
