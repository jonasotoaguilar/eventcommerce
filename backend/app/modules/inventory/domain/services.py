"""Pure domain logic for inventory."""

from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.errors import InsufficientStockError


def reserve_stock(inventory: Inventory, quantity: int) -> None:
    if inventory.available_quantity < quantity:
        raise InsufficientStockError("Not enough stock available")
    inventory.available_quantity -= quantity
    inventory.reserved_quantity += quantity


def adjust_available_stock(inventory: Inventory, delta: int) -> None:
    """Apply a signed operator delta to available stock.

    Negative deltas that would drive ``available_quantity`` below zero
    raise :class:`InsufficientStockError`; reserved stock is untouched.
    """
    if inventory.available_quantity + delta < 0:
        raise InsufficientStockError("Not enough stock available")
    inventory.available_quantity += delta
