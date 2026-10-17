"""Payment repository protocol."""

from typing import Protocol
from uuid import UUID

from app.modules.payments.domain.entities import Payment


class PaymentRepository(Protocol):
    async def get_by_id(self, payment_id: UUID) -> Payment | None: ...
    async def save(self, payment: Payment) -> None: ...
    async def list_by_order_ids(self, order_ids: list[UUID]) -> list[Payment]: ...
