"""Payment repository protocol."""
from typing import Protocol
from uuid import UUID

from app.modules.payments.domain.entities.payment import Payment


class PaymentRepository(Protocol):
    async def get_by_id(self, payment_id: UUID) -> Payment | None: ...
    async def save(self, payment: Payment) -> None: ...

