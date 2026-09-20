"""Cart domain entities.

A cart is owned by exactly one authenticated shopper (``customer_id`` is
the JWT subject, i.e. ``users.id``). There are no guest carts: every
route resolves ownership from the bearer token and never from the body.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class Cart:
    """One active cart per shopper, keyed by JWT subject."""

    id: UUID
    customer_id: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CartLine:
    """A product/quantity line inside a cart (composite identity)."""

    cart_id: UUID
    product_id: str
    quantity: int
