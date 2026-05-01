"""SQLAlchemy implementation of PaymentRepository."""

from uuid import UUID

from app.modules.payments.domain.entities.payment import Payment
from app.modules.payments.domain.repositories.repository import PaymentRepository


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, session: object) -> None:
        self._session = session

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return None

    async def save(self, payment: Payment) -> None:
        pass
