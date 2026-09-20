"""Tests for the shared event envelope vocabulary (U1 payment events)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.shared.messaging.envelope import EventEnvelope


class TestEventEnvelopeVocabulary:
    def test_create_payment_authorized_envelope(self) -> None:
        envelope = EventEnvelope.create(
            event_type="PaymentAuthorized",
            aggregate_id=uuid4(),
            correlation_id=uuid4(),
            payload={"result": "authorized"},
        )
        assert envelope.event_type == "PaymentAuthorized"
        assert envelope.payload == {"result": "authorized"}

    def test_create_payment_rejected_envelope(self) -> None:
        envelope = EventEnvelope.create(
            event_type="PaymentRejected",
            aggregate_id=uuid4(),
            correlation_id=uuid4(),
            payload={"result": "rejected", "reason": "payment_declined"},
        )
        assert envelope.event_type == "PaymentRejected"
        assert envelope.payload["reason"] == "payment_declined"

    def test_existing_order_event_types_still_valid(self) -> None:
        for event_type in (
            "OrderCreated",
            "InventoryReserved",
            "InventoryRejected",
            "OrderConfirmed",
            "OrderCancelled",
        ):
            envelope = EventEnvelope.create(
                event_type=event_type,
                aggregate_id=uuid4(),
                correlation_id=uuid4(),
                payload={},
            )
            assert envelope.event_type == event_type

    def test_unknown_event_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope.create(
                event_type="RefundIssued",
                aggregate_id=uuid4(),
                correlation_id=uuid4(),
                payload={},
            )
