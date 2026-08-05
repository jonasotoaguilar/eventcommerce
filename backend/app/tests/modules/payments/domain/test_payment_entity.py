"""Tests for payment domain models."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.modules.payments.domain.entities import Money, Payment


class TestPayment:
    def test_payment_attributes(self) -> None:
        now = datetime.now(timezone.utc)
        payment = Payment(
            id=uuid4(),
            order_id=uuid4(),
            status="authorized",
            amount=Decimal("50.00"),
            currency="EUR",
            created_at=now,
        )
        assert payment.status == "authorized"
        assert payment.amount == Decimal("50.00")
        assert payment.currency == "EUR"
        assert payment.failure_reason is None

    def test_payment_failure_reason_defaults_to_none(self) -> None:
        now = datetime.now(timezone.utc)
        payment = Payment(
            id=uuid4(),
            order_id=uuid4(),
            status="declined",
            amount=Decimal("19.99"),
            currency="USD",
            created_at=now,
        )
        assert payment.failure_reason is None


class TestMoney:
    def test_money_value_object(self) -> None:
        money = Money(amount=99.99, currency="USD")
        assert money.amount == 99.99
        assert money.currency == "USD"
