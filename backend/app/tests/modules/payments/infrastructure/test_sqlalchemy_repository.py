"""Integration tests for SQLAlchemy payment repository."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.payments.domain.entities import Payment
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


class TestSqlAlchemyPaymentRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        payment = Payment(
            id=uuid4(),
            order_id=uuid4(),
            status="authorized",
            amount=100.0,
            currency="USD",
            created_at=datetime.now(timezone.utc),
        )
        await repo.save(payment)

        found = await repo.get_by_id(payment.id)
        assert found is not None
        assert found.id == payment.id
        assert found.order_id == payment.order_id
        assert found.status == "authorized"
        assert found.amount == 100.0
        assert found.currency == "USD"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        found = await repo.get_by_id(uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_update_status(self, db_session) -> None:
        repo = SqlAlchemyPaymentRepository(db_session)
        payment = Payment(
            id=uuid4(),
            order_id=uuid4(),
            status="authorized",
            amount=50.0,
            currency="EUR",
            created_at=datetime.now(timezone.utc),
        )
        await repo.save(payment)
        payment.status = "failed"
        payment.amount = 0.0
        await repo.save(payment)

        found = await repo.get_by_id(payment.id)
        assert found is not None
        assert found.status == "failed"
        assert found.amount == 0.0
