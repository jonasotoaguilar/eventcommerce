"""Pure domain logic for orders."""
from app.modules.orders.domain.entities.order import Order


def can_transition(from_status: str, to_status: str) -> bool:
    allowed: dict[str, set[str]] = {
        "pending": {"inventory_reserved", "cancelled"},
        "inventory_reserved": {"payment_authorized", "cancelled"},
        "payment_authorized": {"confirmed", "cancelled"},
    }
    return to_status in allowed.get(from_status, set())

