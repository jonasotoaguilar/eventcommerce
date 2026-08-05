"""Tests for ProcessPaymentFailure use case.

Task 2.2: the failure use case persists a ``declined`` Payment carrying
``failure_reason`` and must not mutate the order. The use case receives
no order repository at all, so cancellation is structurally impossible
here — the orchestrator owns the terminal order transition.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.repository import PaymentRepository


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self) -> None:
        self.payments: list[Payment] = []

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        for p in self.payments:
            if p.id == payment_id:
                return p
        return None

    async def save(self, payment: Payment) -> None:
        self.payments.append(payment)


class TestProcessPaymentFailure:
    @pytest.mark.asyncio
    async def test_persists_declined_payment_with_failure_reason(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = ProcessPaymentFailure(repo)
        order_id = uuid4()

        payment = await use_case.execute(
            order_id=order_id,
            amount=Decimal("19.99"),
            currency="USD",
            reason="card_declined",
        )

        assert payment.status == "declined"
        assert payment.failure_reason == "card_declined"
        assert payment.order_id == order_id
        assert payment.amount == Decimal("19.99")
        assert payment.currency == "USD"
        assert len(repo.payments) == 1
        assert repo.payments[0].status == "declined"
        assert repo.payments[0].failure_reason == "card_declined"

    @pytest.mark.asyncio
    async def test_does_not_mutate_order(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = ProcessPaymentFailure(repo)
        order_id = uuid4()

        await use_case.execute(
            order_id=order_id,
            amount=Decimal("5.00"),
            currency="EUR",
            reason="insufficient_funds",
        )

        assert repo.payments[0].order_id == order_id
        assert len(repo.payments) == 1

    def test_use_case_has_no_order_dependency(self) -> None:
        init_params = ProcessPaymentFailure.__init__.__code__.co_varnames
        assert "repository" in init_params
        assert "order" not in init_params

    @pytest.mark.asyncio
    async def test_persisted_payment_has_created_at(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = ProcessPaymentFailure(repo)

        await use_case.execute(
            order_id=uuid4(),
            amount=Decimal("0.00"),
            currency="USD",
            reason="declined",
        )

        created_at = repo.payments[0].created_at
        assert created_at is not None
        assert created_at <= datetime.now(timezone.utc)
