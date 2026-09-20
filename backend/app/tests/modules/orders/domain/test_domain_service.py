"""Tests for order domain service state transitions (five-state lifecycle)."""

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


class TestFiveStateLifecycle:
    """Coverage for the U1 intermediate lifecycle states."""

    def test_pending_to_inventory_reserved(self) -> None:
        assert can_transition("pending", "inventory_reserved") is True

    def test_pending_to_payment_authorized_is_false(self) -> None:
        assert can_transition("pending", "payment_authorized") is False

    def test_inventory_reserved_self_transition(self) -> None:
        assert can_transition("inventory_reserved", "inventory_reserved") is True

    def test_inventory_reserved_to_payment_authorized(self) -> None:
        assert can_transition("inventory_reserved", "payment_authorized") is True

    def test_inventory_reserved_to_cancelled(self) -> None:
        assert can_transition("inventory_reserved", "cancelled") is True

    def test_inventory_reserved_to_confirmed_is_false(self) -> None:
        assert can_transition("inventory_reserved", "confirmed") is False

    def test_inventory_reserved_to_pending_is_false(self) -> None:
        assert can_transition("inventory_reserved", "pending") is False

    def test_payment_authorized_self_transition(self) -> None:
        assert can_transition("payment_authorized", "payment_authorized") is True

    def test_payment_authorized_to_confirmed(self) -> None:
        assert can_transition("payment_authorized", "confirmed") is True

    def test_payment_authorized_to_cancelled(self) -> None:
        assert can_transition("payment_authorized", "cancelled") is True

    def test_payment_authorized_to_pending_is_false(self) -> None:
        assert can_transition("payment_authorized", "pending") is False

    def test_payment_authorized_to_inventory_reserved_is_false(self) -> None:
        assert can_transition("payment_authorized", "inventory_reserved") is False

    def test_terminal_states_reject_intermediates(self) -> None:
        assert can_transition("confirmed", "inventory_reserved") is False
        assert can_transition("confirmed", "payment_authorized") is False
        assert can_transition("cancelled", "inventory_reserved") is False
        assert can_transition("cancelled", "payment_authorized") is False

    def test_unknown_intermediate_from_status(self) -> None:
        assert can_transition("unknown", "inventory_reserved") is False
        assert can_transition("inventory_reserved", "unknown") is False
