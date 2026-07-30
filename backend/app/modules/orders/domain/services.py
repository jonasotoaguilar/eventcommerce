"""Pure domain logic for orders."""

# Phase 1 state machine: pending -> confirmed | cancelled
# Self-transitions are allowed for idempotency.
_PHASE1_ALLOWED: dict[str, set[str]] = {
    "pending": {"pending", "confirmed", "cancelled"},
    "confirmed": {"confirmed"},
    "cancelled": {"cancelled"},
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in _PHASE1_ALLOWED.get(from_status, set())
