"""Pure domain logic for orders."""

# Five-state order lifecycle (U1 expand-order-state-machine):
#   pending -> inventory_reserved | confirmed (sync shortcut) | cancelled
#   inventory_reserved -> payment_authorized | cancelled
#   payment_authorized -> confirmed | cancelled
# Self-transitions are allowed for idempotency on every state; confirmed and
# cancelled are terminal (only self-transitions). The pending -> confirmed
# edge preserves the synchronous checkout contract, which resolves directly
# to a terminal state in one request; the AMQP choreography walks the
# intermediate states.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"pending", "inventory_reserved", "confirmed", "cancelled"},
    "inventory_reserved": {
        "inventory_reserved",
        "payment_authorized",
        "cancelled",
    },
    "payment_authorized": {"payment_authorized", "confirmed", "cancelled"},
    "confirmed": {"confirmed"},
    "cancelled": {"cancelled"},
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, set())
