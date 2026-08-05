"""SQLAlchemy implementation of PaymentRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.repository import PaymentRepository
from app.modules.payments.infrastructure.models import PaymentModel


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        result = await self._session.execute(
            select(PaymentModel).where(PaymentModel.id == payment_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    async def save(self, payment: Payment) -> None:
        result = await self._session.execute(
            select(PaymentModel).where(PaymentModel.id == payment.id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.status = payment.status
            existing.amount = payment.amount
            existing.currency = payment.currency
            existing.failure_reason = payment.failure_reason
        else:
            orm = PaymentModel(
                id=payment.id,
                order_id=payment.order_id,
                status=payment.status,
                amount=payment.amount,
                currency=payment.currency,
                created_at=payment.created_at,
                failure_reason=payment.failure_reason,
            )
            self._session.add(orm)
        await self._session.flush()

    def _to_domain(self, orm: PaymentModel) -> Payment:
        return Payment(
            id=orm.id,
            order_id=orm.order_id,
            status=orm.status,
            amount=orm.amount,
            currency=orm.currency,
            created_at=orm.created_at,
            failure_reason=orm.failure_reason,
        )
