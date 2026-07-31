"""Tests for ProcessPaymentFailure use case."""

from uuid import uuid4

import pytest

from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.repository import PaymentRepository


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self) -> None:
        self.payments: list[Payment] = []

    async def get_by_id(self, payment_id):
        for p in self.payments:
            if p.id == payment_id:
                return p
        return None

    async def save(self, payment: Payment) -> None:
        self.payments.append(payment)


class TestProcessPaymentFailure:
    @pytest.mark.asyncio
    async def test_executes_without_error(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = ProcessPaymentFailure(repo)
        await use_case.execute(order_id=uuid4(), reason="card_declined")
