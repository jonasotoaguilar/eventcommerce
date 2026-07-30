"""Tests for payment domain services."""

import pytest

from app.modules.payments.domain.errors import PaymentRejectedError
from app.modules.payments.domain.services import ensure_payment_amount_is_valid


class TestEnsurePaymentAmountIsValid:
    def test_valid_amount(self) -> None:
        ensure_payment_amount_is_valid(10.0)

    def test_zero_amount_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            ensure_payment_amount_is_valid(0.0)

    def test_negative_amount_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            ensure_payment_amount_is_valid(-5.0)
