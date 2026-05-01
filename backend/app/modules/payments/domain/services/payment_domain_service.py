"""Pure domain logic for payments."""

from app.modules.payments.domain.errors.domain_errors import PaymentRejectedError


def ensure_payment_amount_is_valid(amount: float) -> None:
    if amount <= 0:
        raise PaymentRejectedError("Invalid amount")
