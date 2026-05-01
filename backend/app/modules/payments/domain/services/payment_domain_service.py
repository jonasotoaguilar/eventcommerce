"""Pure domain logic for payments."""
import random

from app.modules.payments.domain.errors.domain_errors import PaymentRejectedError


def authorize_payment(amount: float) -> bool:
    if amount <= 0:
        raise PaymentRejectedError("Invalid amount")
    return random.choice([True, True, True, False])

