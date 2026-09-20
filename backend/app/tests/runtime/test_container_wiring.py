from unittest.mock import AsyncMock, patch
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.messaging_runtime import create_messaging_runtime
from app.modules.inventory.api.container import inventory_container
from app.modules.notifications.api.container import notifications_container
from app.modules.orders.api.container import orders_container
from app.shared.messaging.consumer import MessageConsumer


class _FakeSession(AsyncSession):
    def __init__(self):
        pass


class _S:
    rabbitmq_url = "amqp://x/"
    rabbitmq_outbox_poll_interval = 0.05
    rabbitmq_outbox_batch_size = 10


def _sf():
    return _FakeSession()  # type: ignore


def test_bindings():
    rt = create_messaging_runtime(_S(), _sf)  # type: ignore
    c = rt._consumer  # type: ignore
    assert isinstance(c, MessageConsumer) and len(c._bindings) == 3
    assert {b.queue for b in c._bindings} == {
        "inventory.order_created",
        "orders.inventory_result",
        "notifications.order_terminal",
    }
    assert sorted(e for b in c._bindings for e in b.event_types) == sorted(
        [
            "OrderCreated",
            "InventoryReserved",
            "InventoryRejected",
            "OrderConfirmed",
            "OrderCancelled",
        ]
    )
    assert c._session_factory is _sf
    assert (
        create_messaging_runtime(_S(), _sf, consumer=AsyncMock())._consumer is not None
    )  # type: ignore
    s1, s2 = _FakeSession(), _FakeSession()  # type: ignore
    f = next(
        b.handler_factory for b in c._bindings if b.queue == "inventory.order_created"
    )
    assert f(s1) is not f(s2)
    with pytest.raises(Exception):
        orders_container.get_order_status()


@pytest.mark.asyncio
async def test_wiring():
    s = _FakeSession()  # type: ignore
    from app.modules.inventory.api.container import InventoryContainer
    from app.modules.orders.api.container import OrdersContainer

    oc, ic = OrdersContainer(), InventoryContainer()
    oc.session.override(s)
    ic.session.override(s)
    gs = oc.get_order_status()
    ic.order_status_query.override(gs)
    w = ic.process_inventory_reservation()
    assert w._inventory_repo._session is s  # type: ignore
    assert w._order_status._repository._session is s  # type: ignore
    rt = create_messaging_runtime(_S(), _sf)  # type: ignore
    inv = next(
        b.handler_factory
        for b in rt._consumer._bindings
        if b.queue == "inventory.order_created"
    )  # type: ignore
    ord_f = next(
        b.handler_factory
        for b in rt._consumer._bindings
        if b.queue == "orders.inventory_result"
    )  # type: ignore
    notif = next(
        b.handler_factory
        for b in rt._consumer._bindings
        if b.queue == "notifications.order_terminal"
    )  # type: ignore
    with patch(
        "app.modules.inventory.application.process_inventory_reservation.ProcessInventoryReservation.execute",
        new_callable=AsyncMock,
    ) as m:
        h = inv(s)
        eid, aid = str(uuid4()), str(uuid4())
        with pytest.raises(KeyError):
            await h(
                payload={}, event_id=eid, event_type="OrderCreated", aggregate_id=aid
            )
        with pytest.raises(ValueError):
            await h(
                payload={"items": []},
                event_id=eid,
                event_type="OrderCreated",
                aggregate_id="bad",
            )
        await h(
            payload={"items": [{"product_id": "p1", "quantity": 1}]},
            event_id=eid,
            event_type="OrderCreated",
            aggregate_id=aid,
        )
        assert m.call_args.kwargs["items"] == [{"product_id": "p1", "quantity": 1}]
    with patch(
        "app.modules.orders.application.process_inventory_result.ProcessOrderInventoryResult.execute",
        new_callable=AsyncMock,
    ) as m:
        h = ord_f(s)
        eid, aid = str(uuid4()), str(uuid4())
        await h(
            payload={}, event_id=eid, event_type="InventoryReserved", aggregate_id=aid
        )
        assert m.call_args.kwargs["result"] == "reserved"
        with pytest.raises(ValueError):
            await h(
                payload={}, event_id=eid, event_type="OrderCreated", aggregate_id=aid
            )
    with patch(
        "app.modules.notifications.application.process_order_notification.ProcessOrderNotification.execute",
        new_callable=AsyncMock,
    ) as m:
        h = notif(s)
        eid, aid = str(uuid4()), str(uuid4())
        await h(
            payload={"x": 1},
            event_id=eid,
            event_type="OrderConfirmed",
            aggregate_id=aid,
        )
        m.assert_awaited_once()


def test_containers():
    s = _FakeSession()  # type: ignore
    orders_container.session.override(s)
    try:
        from app.modules.orders.application.get_order_status import GetOrderStatus

        assert isinstance(orders_container.get_order_status(), GetOrderStatus)
    finally:
        orders_container.session.reset_override()

    class _QS:
        async def get_status(self, oid):  # type: ignore
            return None

    fq = _QS()
    inventory_container.session.override(s)
    inventory_container.order_status_query.override(fq)
    try:
        assert inventory_container.process_inventory_reservation()._order_status is fq  # type: ignore
    finally:
        inventory_container.session.reset_override()
        inventory_container.order_status_query.reset_override()
    notifications_container.session.override(s)
    assert (
        notifications_container.process_order_notification()._notifier._repository._session  # type: ignore[attr-defined]
        is s
    )  # type: ignore
    notifications_container.session.reset_override()


def test_cart_container_wires_use_cases_to_the_request_session():
    from app.modules.cart.api.container import cart_container
    from app.modules.cart.application.add_item import AddCartItem
    from app.modules.cart.application.get_cart import GetCart
    from app.modules.cart.application.remove_item import RemoveCartItem
    from app.modules.cart.application.set_item_quantity import SetCartItemQuantity

    s = _FakeSession()  # type: ignore
    cart_container.session.override(s)
    try:
        get = cart_container.get_cart()
        add = cart_container.add_item()
        setter = cart_container.set_quantity()
        remove = cart_container.remove_item()
    finally:
        cart_container.session.reset_override()
    assert isinstance(get, GetCart)
    assert isinstance(add, AddCartItem)
    assert isinstance(setter, SetCartItemQuantity)
    assert isinstance(remove, RemoveCartItem)
    for use_case in (get, add, setter, remove):
        assert use_case._carts._session is s  # type: ignore
        assert use_case._products._session is s  # type: ignore


def test_cart_routes_registered():
    from app.app import create_app

    app = create_app()
    found = {
        (getattr(r, "path", ""), method)
        for r in app.routes
        for method in (sorted(getattr(r, "methods", set()) or []))
    }
    assert ("/api/v1/cart", "GET") in found
    assert ("/api/v1/cart/items", "POST") in found
    assert ("/api/v1/cart/items/{product_id}", "PATCH") in found
    assert ("/api/v1/cart/items/{product_id}", "DELETE") in found


def test_checkout_container_wires_cart_and_catalog_repos_to_the_request_session():
    from app.modules.checkout.api.container import checkout_container

    s = _FakeSession()  # type: ignore
    checkout_container.session.override(s)
    try:
        checkout = checkout_container.checkout()
    finally:
        checkout_container.session.reset_override()
    assert checkout._cart_repo._session is s  # type: ignore
    assert checkout._product_repo._session is s  # type: ignore
    assert checkout._session is s
