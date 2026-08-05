"""ProcessPaymentFailure use case.

Persists a ``declined`` Payment record carrying the failure reason. The
use case has no order dependency: it never confirms or cancels an order —
the orchestrator owns the terminal order transition.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.repository import PaymentRepository


class ProcessPaymentFailure:
    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        order_id: UUID,
        amount: Decimal,
        currency: str,
        reason: str,
    ) -> Payment:
        payment = Payment(
            id=uuid4(),
            order_id=order_id,
            status="declined",
            amount=amount,
            currency=currency,
            created_at=datetime.now(timezone.utc),
            failure_reason=reason,
        )
        await self._repository.save(payment)
        return payment
