"""Order item value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderItem:
    product_id: str
    quantity: int
