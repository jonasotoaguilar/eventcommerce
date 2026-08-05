"""AuthorizePayment use case."""

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.errors import PaymentRejectedError
from app.modules.payments.domain.policy import is_payment_approved
from app.modules.payments.domain.repository import PaymentRepository
from app.modules.payments.domain.services import ensure_payment_amount_is_valid


class AuthorizePayment:
    def __init__(
        self,
        repository: PaymentRepository,
        approval_policy: Callable[[str, Decimal, str], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._approval_policy = approval_policy or is_payment_approved

    async def execute(self, order_id: UUID, amount: Decimal, currency: str) -> Payment:
        ensure_payment_amount_is_valid(amount)
        if not self._approval_policy(str(order_id), amount, currency):
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
