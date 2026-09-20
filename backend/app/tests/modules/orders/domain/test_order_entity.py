"""Tests for Order domain entity."""

from uuid import uuid4

import pytest

from app.modules.orders.domain.entities import Order
from app.modules.orders.domain.errors import InvalidStateTransitionError
from app.modules.orders.domain.entities import OrderItem


class TestOrderEntity:
    """Unit tests for Order entity."""

    def test_order_has_items_field(self) -> None:
        item = OrderItem(product_id="prod_1", quantity=2)
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[item],
        )
        assert order.items == [item]

    def test_order_total_items(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[
                OrderItem(product_id="prod_1", quantity=2),
                OrderItem(product_id="prod_2", quantity=3),
            ],
        )
        assert len(order.items) == 2

    def test_confirm_from_pending(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        order.confirm()
        assert order.status == "confirmed"

    def test_cancel_from_pending(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="pending",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        order.cancel(reason="out_of_stock")
        assert order.status == "cancelled"
        assert order.cancel_reason == "out_of_stock"

    def test_confirm_idempotent(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="confirmed",
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        order.confirm()
        assert order.status == "confirmed"

    def test_cancel_idempotent(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="cancelled",
            cancel_reason="out_of_stock",
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        order.cancel(reason="duplicate")
        assert order.status == "cancelled"
        assert order.cancel_reason == "out_of_stock"

    def test_confirm_after_cancel_raises(self) -> None:
        order = Order(
            id=uuid4(),
            customer_id="cus_1",
            status="cancelled",
            cancel_reason="out_of_stock",
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )
        with pytest.raises(InvalidStateTransitionError):
            order.confirm()

    def _order_with_status(self, status: str) -> Order:
        return Order(
            id=uuid4(),
            customer_id="cus_1",
            status=status,
            cancel_reason=None,
            created_at=None,  # type: ignore[arg-type]
            updated_at=None,  # type: ignore[arg-type]
            items=[],
        )

    def test_reserve_inventory_from_pending(self) -> None:
        order = self._order_with_status("pending")
        order.reserve_inventory()
        assert order.status == "inventory_reserved"

    def test_reserve_inventory_idempotent(self) -> None:
        order = self._order_with_status("inventory_reserved")
        order.reserve_inventory()
        assert order.status == "inventory_reserved"

    def test_reserve_inventory_from_terminal_raises(self) -> None:
        for status in ("payment_authorized", "confirmed", "cancelled"):
            with pytest.raises(InvalidStateTransitionError):
                self._order_with_status(status).reserve_inventory()

    def test_authorize_payment_from_inventory_reserved(self) -> None:
        order = self._order_with_status("inventory_reserved")
        order.authorize_payment()
        assert order.status == "payment_authorized"

    def test_authorize_payment_idempotent(self) -> None:
        order = self._order_with_status("payment_authorized")
        order.authorize_payment()
        assert order.status == "payment_authorized"

    def test_authorize_payment_from_pending_raises(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            self._order_with_status("pending").authorize_payment()

    def test_authorize_payment_from_terminal_raises(self) -> None:
        for status in ("confirmed", "cancelled"):
            with pytest.raises(InvalidStateTransitionError):
                self._order_with_status(status).authorize_payment()

    def test_confirm_from_payment_authorized(self) -> None:
        order = self._order_with_status("payment_authorized")
        order.confirm()
        assert order.status == "confirmed"

    def test_confirm_from_inventory_reserved_raises(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            self._order_with_status("inventory_reserved").confirm()

    def test_cancel_from_intermediate_states(self) -> None:
        for status in ("pending", "inventory_reserved", "payment_authorized"):
            order = self._order_with_status(status)
            order.cancel(reason="customer_request")
            assert order.status == "cancelled"
            assert order.cancel_reason == "customer_request"

    def test_full_choreography_walk(self) -> None:
        order = self._order_with_status("pending")
        order.reserve_inventory()
        order.authorize_payment()
        order.confirm()
        assert order.status == "confirmed"
