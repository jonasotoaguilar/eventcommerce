"""Pure domain logic for payments."""

from decimal import Decimal

from app.modules.payments.domain.errors import PaymentRejectedError


def ensure_payment_amount_is_valid(amount: Decimal) -> None:
    if amount <= 0:
        raise PaymentRejectedError("Invalid amount")
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise PaymentRejectedError("Invalid amount: more than two decimal places")
