"""Tests for payment domain models."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.payments.domain.entities import Money, Payment


class TestPayment:
    def test_payment_attributes(self) -> None:
        now = datetime.now(timezone.utc)
        payment = Payment(
            id=uuid4(),
            order_id=uuid4(),
            status="authorized",
            amount=50.0,
            currency="EUR",
            created_at=now,
        )
        assert payment.status == "authorized"
        assert payment.amount == 50.0
        assert payment.currency == "EUR"


class TestMoney:
    def test_money_value_object(self) -> None:
        money = Money(amount=99.99, currency="USD")
        assert money.amount == 99.99
        assert money.currency == "USD"
