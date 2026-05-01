"""AuthorizePayment use case."""

import random
from collections.abc import Callable
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.modules.payments.domain.entities.payment import Payment
from app.modules.payments.domain.errors.domain_errors import PaymentRejectedError
from app.modules.payments.domain.repositories.repository import PaymentRepository
from app.modules.payments.domain.services.payment_domain_service import (
    ensure_payment_amount_is_valid,
)


class AuthorizePayment:
    def __init__(
        self,
        repository: PaymentRepository,
        approval_policy: Callable[[float, str], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._approval_policy = approval_policy or self._simulate_provider_authorization

    @staticmethod
    def _simulate_provider_authorization(amount: float, currency: str) -> bool:
        del amount, currency
        return random.choice([True, True, True, False])

    async def execute(self, order_id: UUID, amount: float, currency: str) -> Payment:
        ensure_payment_amount_is_valid(amount)
        if not self._approval_policy(amount, currency):
            raise PaymentRejectedError("Payment was rejected by provider")
        payment = Payment(
            id=uuid4(),
            order_id=order_id,
            status="authorized",
            amount=amount,
            currency=currency,
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.save(payment)
        return payment
