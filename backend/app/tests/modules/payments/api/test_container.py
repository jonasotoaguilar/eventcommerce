"""RED tests for the S3c2a payments container providers (task 3.17).

Covers wiring of ``payment_repo``, ``AuthorizePayment`` and
``ProcessPaymentFailure`` into ``PaymentsContainer``: providers resolve
only under a request-session override and share that single session.
"""

from typing import cast

import pytest
from dependency_injector import errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.api.container import payments_container
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


class _FakeSession(AsyncSession):
    """Minimal AsyncSession stand-in for wiring assertions."""

    def __init__(self) -> None:
        pass


def test_payments_container_requires_a_request_session_override() -> None:
    with pytest.raises(errors.Error):
        payments_container.payment_repo()
    with pytest.raises(errors.Error):
        payments_container.authorize_payment()
    with pytest.raises(errors.Error):
        payments_container.process_payment_failure()


def test_payments_container_wires_payment_repo_to_the_request_session() -> None:
    session = _FakeSession()
    payments_container.session.override(session)
    try:
        repo = payments_container.payment_repo()
    finally:
        payments_container.session.reset_override()

    assert isinstance(repo, SqlAlchemyPaymentRepository)
    assert repo._session is session


def test_payments_container_wires_use_cases_to_the_request_session() -> None:
    session = _FakeSession()
    payments_container.session.override(session)
    try:
        authorize = payments_container.authorize_payment()
        failure = payments_container.process_payment_failure()
    finally:
        payments_container.session.reset_override()

    assert isinstance(authorize, AuthorizePayment)
    assert cast(SqlAlchemyPaymentRepository, authorize._repository)._session is session
    assert isinstance(failure, ProcessPaymentFailure)
    assert cast(SqlAlchemyPaymentRepository, failure._repository)._session is session
