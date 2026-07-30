"""Tests for AuthorizePayment use case."""

from uuid import uuid4

import pytest

from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.domain.errors import PaymentRejectedError
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


class TestAuthorizePayment:
    @pytest.mark.asyncio
    async def test_authorizes_successfully(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = AuthorizePayment(repo, approval_policy=lambda amount, currency: True)
        payment = await use_case.execute(order_id=uuid4(), amount=100.0, currency="USD")

        assert payment.status == "authorized"
        assert payment.amount == 100.0
        assert len(repo.payments) == 1

    @pytest.mark.asyncio
    async def test_rejected_by_provider_raises(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = AuthorizePayment(
            repo, approval_policy=lambda amount, currency: False
        )
        with pytest.raises(PaymentRejectedError, match="rejected by provider"):
            await use_case.execute(order_id=uuid4(), amount=100.0, currency="USD")

    @pytest.mark.asyncio
    async def test_invalid_amount_raises(self) -> None:
        repo = InMemoryPaymentRepository()
        use_case = AuthorizePayment(repo, approval_policy=lambda amount, currency: True)
        with pytest.raises(PaymentRejectedError, match="Invalid amount"):
            await use_case.execute(order_id=uuid4(), amount=0.0, currency="USD")
