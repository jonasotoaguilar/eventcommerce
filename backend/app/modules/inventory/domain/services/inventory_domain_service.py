"""Pure domain logic for inventory."""
from app.modules.inventory.domain.entities.inventory import Inventory
from app.modules.inventory.domain.errors.domain_errors import InsufficientStockError


def reserve_stock(inventory: Inventory, quantity: int) -> None:
    if inventory.available_quantity < quantity:
        raise InsufficientStockError("Not enough stock available")
    inventory.available_quantity -= quantity
    inventory.reserved_quantity += quantity

