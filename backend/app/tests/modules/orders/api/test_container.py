"""RED tests for the S3c2a orders container providers (task 3.17).

Covers wiring of ``ConfirmOrder``, ``CancelOrder`` and
``ProcessOrderInventoryResult`` into ``OrdersContainer``: all providers
must resolve only under a request-session override, and every resolved
use case must share that single session across its dependencies.
"""

from typing import cast

import pytest
from dependency_injector import errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.api.container import orders_container
from app.modules.orders.application.cancel_order import CancelOrder
from app.modules.orders.application.confirm_order import ConfirmOrder
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.application.get_order import GetOrder
from app.modules.orders.application.process_inventory_result import (
    ProcessOrderInventoryResult,
)
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.events.event_repository import SqlAlchemyEventRepository


class _FakeSession(AsyncSession):
    """Minimal AsyncSession stand-in for wiring assertions."""

    def __init__(self) -> None:
        pass


def test_orders_container_requires_a_request_session_override() -> None:
    with pytest.raises(errors.Error):
        orders_container.confirm_order()
    with pytest.raises(errors.Error):
        orders_container.cancel_order()
    with pytest.raises(errors.Error):
        orders_container.process_order_inventory_result()


def test_orders_container_wires_confirm_and_cancel_to_the_request_session() -> None:
    session = _FakeSession()
    orders_container.session.override(session)
    try:
        confirm_order = orders_container.confirm_order()
        cancel_order = orders_container.cancel_order()
    finally:
        orders_container.session.reset_override()

    assert isinstance(confirm_order, ConfirmOrder)
    assert (
        cast(SqlAlchemyOrderRepository, confirm_order._repository)._session is session
    )
    assert isinstance(cancel_order, CancelOrder)
    assert cast(SqlAlchemyOrderRepository, cancel_order._repository)._session is session


def test_orders_container_wires_process_order_inventory_result_to_the_session() -> None:
    session = _FakeSession()
    orders_container.session.override(session)
    try:
        use_case = orders_container.process_order_inventory_result()
    finally:
        orders_container.session.reset_override()

    assert isinstance(use_case, ProcessOrderInventoryResult)
    assert cast(SqlAlchemyOrderRepository, use_case._order_repo)._session is session
    assert cast(SqlAlchemyEventRepository, use_case._event_repo)._session is session
    assert use_case._outbox._session is session
    assert use_case._idempotency._session is session


def test_orders_container_existing_providers_still_resolve() -> None:
    session = _FakeSession()
    orders_container.session.override(session)
    try:
        assert isinstance(orders_container.create_order(), CreateOrder)
        assert isinstance(orders_container.get_order(), GetOrder)
    finally:
        orders_container.session.reset_override()
