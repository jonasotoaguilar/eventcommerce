"""ProcessPaymentFailure use case."""
from uuid import UUID

from app.modules.payments.domain.repositories.repository import PaymentRepository


class ProcessPaymentFailure:
    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    async def execute(self, order_id: UUID, reason: str) -> None:
        pass

