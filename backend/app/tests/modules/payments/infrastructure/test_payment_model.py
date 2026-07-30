"""Tests for payments ORM models."""

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
