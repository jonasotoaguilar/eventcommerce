"""Pure domain logic for orders."""


def can_transition(from_status: str, to_status: str) -> bool:
    allowed: dict[str, set[str]] = {
        "pending": {"inventory_reserved", "cancelled"},
        "inventory_reserved": {"payment_authorized", "cancelled"},
        "payment_authorized": {"confirmed", "cancelled"},
    }
    return to_status in allowed.get(from_status, set())
