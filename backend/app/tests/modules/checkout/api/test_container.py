"""RED tests for the S3c2a checkout container (tasks 3.15).

Covers request-local ``AsyncSession`` wiring: every repository and use
case resolved from ``CheckoutContainer`` must share the session provided
through the ``session`` override, no global session may exist, and each
resolve must produce fresh instances bound to the request session.
"""

from typing import cast

import pytest
from dependency_injector import errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.api.container import checkout_container
from app.modules.checkout.application.checkout import Checkout
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)


class _FakeSession(AsyncSession):
    """Minimal AsyncSession stand-in for wiring assertions."""

    def __init__(self) -> None:
        pass


def test_checkout_container_requires_a_request_session_override() -> None:
    with pytest.raises(errors.Error):
        checkout_container.checkout()


def test_checkout_container_rejects_non_async_session_override() -> None:
    checkout_container.session.override(object())
    try:
        with pytest.raises(errors.Error):
            checkout_container.checkout()
    finally:
        checkout_container.session.reset_override()


def test_checkout_container_wires_every_dependency_to_the_request_session() -> None:
    session = _FakeSession()
    checkout_container.session.override(session)
    try:
        checkout = checkout_container.checkout()
    finally:
        checkout_container.session.reset_override()

    assert isinstance(checkout, Checkout)
    assert checkout._session is session
    assert cast(SqlAlchemyOrderRepository, checkout._order_repo)._session is session
    assert (
        cast(SqlAlchemyInventoryRepository, checkout._inventory_repo)._session
        is session
    )
    assert checkout._outbox._session is session
    assert checkout._idempotency._session is session
    assert checkout._create_order._event_repo._session is session
    assert checkout._create_order._outbox._session is session
    assert (
        cast(SqlAlchemyOrderRepository, checkout._create_order._repository)._session
        is session
    )
    assert (
        cast(
            SqlAlchemyPaymentRepository, checkout._authorize_payment._repository
        )._session
        is session
    )
    assert (
        cast(
            SqlAlchemyPaymentRepository,
            checkout._process_payment_failure._repository,
        )._session
        is session
    )
    assert (
        cast(SqlAlchemyNotificationRepository, checkout._notifier._repository)._session
        is session
    )


def test_checkout_container_resolves_fresh_instances_per_request() -> None:
    session = _FakeSession()
    checkout_container.session.override(session)
    try:
        first = checkout_container.checkout()
        second = checkout_container.checkout()
    finally:
        checkout_container.session.reset_override()

    assert first is not second
    assert first._session is second._session is session
