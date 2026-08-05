"""Tests for payments ORM models."""

from sqlalchemy import Numeric, Text

from app.modules.payments.infrastructure.models import PaymentModel


class TestPaymentModel:
    def test_payment_columns(self) -> None:
        cols = {c.name for c in PaymentModel.__table__.columns}
        assert "id" in cols
        assert "order_id" in cols
        assert "status" in cols
        assert "amount" in cols
        assert "currency" in cols
        assert "created_at" in cols
        assert "failure_reason" in cols

    def test_amount_column_is_numeric_11_2(self) -> None:
        col = PaymentModel.__table__.c.amount
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 11
        assert col.type.scale == 2
        assert not col.nullable

    def test_failure_reason_column_is_nullable_text(self) -> None:
        col = PaymentModel.__table__.c.failure_reason
        assert isinstance(col.type, Text)
        assert col.nullable
