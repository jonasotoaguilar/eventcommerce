"""AuthorizePayment use case."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.modules.payments.domain.entities.payment import Payment
from app.modules.payments.domain.errors.domain_errors import PaymentRejectedError
from app.modules.payments.domain.repositories.repository import PaymentRepository
from app.modules.payments.domain.services.payment_domain_service import authorize_payment


class AuthorizePayment:
    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID, amount: float, currency: str) -> Payment:
        if not authorize_payment(amount):
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

