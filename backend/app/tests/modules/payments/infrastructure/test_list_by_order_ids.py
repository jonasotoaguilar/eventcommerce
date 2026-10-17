"""Contract tests for PaymentRepository.list_by_order_ids (operator queue read)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.payments.domain.entities import Payment
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


def _payment(order_id: UUID, amount: str = "10.00") -> Payment:
    now = datetime(2024, 5, 1, 12, 0, 0)
    return Payment(
        id=uuid4(),
        order_id=order_id,
        status="authorized",
        amount=Decimal(amount),
        currency="USD",
        created_at=now,
    )


class TestListByOrderIds:
    @pytest.mark.asyncio
    async def test_returns_payments_for_requested_orders_only(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        wanted_a, wanted_b, other = uuid4(), uuid4(), uuid4()
        payment_a = _payment(wanted_a, "10.00")
        payment_b = _payment(wanted_b, "20.00")
        unrelated = _payment(other, "99.99")
        for payment in (payment_a, payment_b, unrelated):
            await repo.save(payment)

        rows = await repo.list_by_order_ids([wanted_a, wanted_b])

        assert {p.id for p in rows} == {payment_a.id, payment_b.id}
        assert {p.order_id for p in rows} == {wanted_a, wanted_b}

    @pytest.mark.asyncio
    async def test_returns_multiple_payments_per_order(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        order_id = uuid4()
        first = _payment(order_id, "10.00")
        second = _payment(order_id, "20.00")
        await repo.save(first)
        await repo.save(second)

        rows = await repo.list_by_order_ids([order_id])

        assert {p.id for p in rows} == {first.id, second.id}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        await repo.save(_payment(uuid4()))

        assert await repo.list_by_order_ids([]) == []

    @pytest.mark.asyncio
    async def test_unknown_order_returns_empty(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)

        assert await repo.list_by_order_ids([uuid4()]) == []
