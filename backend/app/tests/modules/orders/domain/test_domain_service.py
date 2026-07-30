"""Tests for order domain service state transitions (Phase 1)."""

from app.modules.orders.domain.services import can_transition


class TestCanTransition:
    """Unit tests for order state transitions."""

    def test_pending_to_confirmed(self) -> None:
        assert can_transition("pending", "confirmed") is True

    def test_pending_to_cancelled(self) -> None:
        assert can_transition("pending", "cancelled") is True

    def test_pending_to_pending(self) -> None:
        assert can_transition("pending", "pending") is True

    def test_confirmed_to_cancelled(self) -> None:
        assert can_transition("confirmed", "cancelled") is False

    def test_cancelled_to_confirmed(self) -> None:
        assert can_transition("cancelled", "confirmed") is False

    def test_confirmed_to_confirmed(self) -> None:
        assert can_transition("confirmed", "confirmed") is True

    def test_cancelled_to_cancelled(self) -> None:
        assert can_transition("cancelled", "cancelled") is True

    def test_unknown_from_status(self) -> None:
        assert can_transition("unknown", "confirmed") is False

    def test_unknown_to_status(self) -> None:
        assert can_transition("pending", "unknown") is False
