"""Tests for order domain event vocabulary (U1 payment result events)."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.orders.domain.events import (
    InventoryRejected,
    InventoryReserved,
    OrderCreated,
    PaymentAuthorized,
    PaymentRejected,
)


class TestOrderEventVocabulary:
    def test_payment_authorized_defaults(self) -> None:
        aggregate_id = uuid4()
        event = PaymentAuthorized(
            event_id=uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(timezone.utc),
        )
        assert event.order_id == aggregate_id
        assert event.result == "authorized"

    def test_payment_rejected_defaults(self) -> None:
        aggregate_id = uuid4()
        event = PaymentRejected(
            event_id=uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(timezone.utc),
        )
        assert event.order_id == aggregate_id
        assert event.result == "rejected"
        assert event.reason == ""

    def test_payment_rejected_carries_reason(self) -> None:
        event = PaymentRejected(
            event_id=uuid4(),
            aggregate_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            reason="payment_declined",
        )
        assert event.reason == "payment_declined"

    def test_existing_inventory_events_unchanged(self) -> None:
        aggregate_id = uuid4()
        reserved = InventoryReserved(
            event_id=uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(timezone.utc),
        )
        assert reserved.order_id == aggregate_id
        assert reserved.result == "reserved"

        rejected = InventoryRejected(
            event_id=uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(timezone.utc),
            reason="insufficient_stock",
        )
        assert rejected.order_id == aggregate_id
        assert rejected.result == "rejected"
        assert rejected.reason == "insufficient_stock"

    def test_order_created_unchanged(self) -> None:
        aggregate_id = uuid4()
        event = OrderCreated(
            event_id=uuid4(),
            aggregate_id=aggregate_id,
            occurred_at=datetime.now(timezone.utc),
            customer_id="cus_1",
        )
        assert event.order_id == aggregate_id
        assert event.customer_id == "cus_1"
        assert event.items == []
