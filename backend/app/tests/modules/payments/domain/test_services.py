"""Tests for payment domain services."""

from decimal import Decimal

import pytest

from app.modules.payments.domain.errors import PaymentRejectedError
from app.modules.payments.domain.services import ensure_payment_amount_is_valid


class TestEnsurePaymentAmountIsValid:
    def test_valid_amount(self) -> None:
        ensure_payment_amount_is_valid(Decimal("10.00"))

    def test_zero_amount_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            ensure_payment_amount_is_valid(Decimal("0.00"))

    def test_negative_amount_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            ensure_payment_amount_is_valid(Decimal("-5.00"))

    def test_negative_amount_without_decimals_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            ensure_payment_amount_is_valid(Decimal("-5"))

    def test_amount_with_two_decimals_is_accepted(self) -> None:
        ensure_payment_amount_is_valid(Decimal("19.99"))

    def test_amount_with_one_decimal_is_accepted(self) -> None:
        ensure_payment_amount_is_valid(Decimal("19.9"))

    def test_amount_without_decimals_is_accepted(self) -> None:
        ensure_payment_amount_is_valid(Decimal("19"))

    def test_amount_with_three_decimals_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="decimal places"):
            ensure_payment_amount_is_valid(Decimal("19.999"))

    def test_amount_with_more_than_two_decimals_raises(self) -> None:
        with pytest.raises(PaymentRejectedError, match="decimal places"):
            ensure_payment_amount_is_valid(Decimal("0.001"))
