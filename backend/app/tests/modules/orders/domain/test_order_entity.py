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
