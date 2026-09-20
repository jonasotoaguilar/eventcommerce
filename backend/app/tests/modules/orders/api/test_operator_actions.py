"""U4 operator confirm/cancel API tests for the orders router.

Operator-only actions on ``/api/v1/orders``:

* ``POST /{order_id}/confirm`` allows ``payment_authorized -> confirmed``
  (idempotent ``confirmed`` retry), 409 on any other state, 404 when
  missing.
* ``POST /{order_id}/cancel`` with a validated reason body allows
  cancellation from ``pending``/``inventory_reserved``/
  ``payment_authorized`` (idempotent ``cancelled`` retry), 409 on
  ``confirmed``, 404 when missing.
* Both require JWT role ``operator`` (401 anonymous, 403 otherwise) and
  emit terminal timeline + outbox events exactly once per transition.
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.shared.db.session import get_db_session
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ID = UUID("22222222-2222-2222-2222-222222222222")
OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")


def _user(user_id: UUID, role: str = "shopper") -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(OWNER_ID)}


@pytest.fixture
def app(engine, auth):
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return auth["user"]

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_current_user
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def _create(client: TestClient) -> str:
    response = client.post(
        "/api/v1/orders", json={"items": [{"product_id": "prod_1", "quantity": 1}]}
    )
    assert response.status_code == 201
    return response.json()["order_id"]


def _set_status(engine, order_id: str, status: str, reason: str | None = None) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            repo = SqlAlchemyOrderRepository(session)
            order = await repo.get_by_id(UUID(order_id))
            assert order is not None
            order.status = status
            order.cancel_reason = reason
            await repo.save(order)
            await session.commit()

    asyncio.run(_go())


def _outbox_for(
    engine, order_id: str, event_type: str | None = None
) -> list[tuple[str, dict]]:
    """Pending outbox rows for one order, optionally scoped to one event type.

    Order creation always leaves an ``OrderCreated`` row behind, so
    terminal-event assertions scope to the terminal type under test.
    """

    async def _go() -> list[tuple[str, dict]]:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            repo = SqlAlchemyOutboxRepository(session)
            return [
                (e.event_type, e.payload)
                for e in await repo.get_pending(limit=50)
                if e.aggregate_id == order_id
                and (event_type is None or e.event_type == event_type)
            ]

    return asyncio.run(_go())


def _as_operator(auth) -> None:
    auth["user"] = _user(OPERATOR_ID, role="operator")


class TestConfirmAuthorization:
    def test_anonymous_confirm_returns_401(self, client: TestClient, app) -> None:
        order_id = _create(client)

        app.dependency_overrides.pop(get_current_user)

        response = client.post(f"/api/v1/orders/{order_id}/confirm")

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_shopper_confirm_returns_403_without_leak(
        self, client: TestClient, app, auth, engine
    ) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "payment_authorized")

        response = client.post(f"/api/v1/orders/{order_id}/confirm")

        assert response.status_code == 403
        assert "detail" in response.json()

        missing = client.post(f"/api/v1/orders/{uuid4()}/confirm")

        assert missing.status_code == 403

    def test_operator_can_confirm_foreign_order(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "payment_authorized")

        _as_operator(auth)
        response = client.post(f"/api/v1/orders/{order_id}/confirm")

        assert response.status_code == 200
        assert response.json() == {"order_id": order_id, "status": "confirmed"}


class TestConfirmTransitions:
    def test_confirm_payment_authorized(self, client: TestClient, auth, engine) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "payment_authorized")

        _as_operator(auth)
        response = client.post(f"/api/v1/orders/{order_id}/confirm")

        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

        stored = client.get(f"/api/v1/orders/{order_id}")
        assert stored.status_code == 200
        assert stored.json()["status"] == "confirmed"

    def test_confirm_idempotent_retry_emits_once(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "payment_authorized")

        _as_operator(auth)
        assert client.post(f"/api/v1/orders/{order_id}/confirm").status_code == 200
        retry = client.post(f"/api/v1/orders/{order_id}/confirm")

        assert retry.status_code == 200
        assert retry.json()["status"] == "confirmed"
        assert _outbox_for(engine, order_id, "OrderConfirmed") == [
            ("OrderConfirmed", {"status": "confirmed"})
        ]

    def test_confirm_rejects_non_authorized_states(
        self, client: TestClient, auth, engine
    ) -> None:
        _as_operator(auth)
        for status in ("pending", "inventory_reserved", "cancelled"):
            order_id = _create(client)
            _set_status(
                engine,
                order_id,
                status,
                reason="operator_cancelled" if status == "cancelled" else None,
            )

            response = client.post(f"/api/v1/orders/{order_id}/confirm")

            assert response.status_code == 409
            assert "detail" in response.json()
            assert client.get(f"/api/v1/orders/{order_id}").json()["status"] == status
            assert _outbox_for(engine, order_id, "OrderConfirmed") == []
            assert _outbox_for(engine, order_id, "OrderCancelled") == []

    def test_confirm_missing_order_returns_404(self, client: TestClient, auth) -> None:
        _as_operator(auth)

        response = client.post(f"/api/v1/orders/{uuid4()}/confirm")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_confirm_emits_timeline_and_outbox_once(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "payment_authorized")

        _as_operator(auth)
        assert client.post(f"/api/v1/orders/{order_id}/confirm").status_code == 200
        assert client.post(f"/api/v1/orders/{order_id}/confirm").status_code == 200

        timeline = client.get(f"/api/v1/orders/{order_id}/timeline")
        assert timeline.status_code == 200
        confirmed = [e for e in timeline.json() if e["event_type"] == "OrderConfirmed"]
        assert len(confirmed) == 1
        assert confirmed[0]["payload"] == {"status": "confirmed"}
        assert _outbox_for(engine, order_id, "OrderConfirmed") == [
            ("OrderConfirmed", {"status": "confirmed"})
        ]


class TestCancelAuthorization:
    def test_anonymous_cancel_returns_401(self, client: TestClient, app) -> None:
        order_id = _create(client)

        app.dependency_overrides.pop(get_current_user)

        response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

        assert response.status_code == 401

    def test_shopper_cancel_returns_403_without_leak(
        self, client: TestClient, engine
    ) -> None:
        order_id = _create(client)

        response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

        assert response.status_code == 403
        assert "detail" in response.json()

        missing = client.post(f"/api/v1/orders/{uuid4()}/cancel", json={})

        assert missing.status_code == 403


class TestCancelTransitions:
    def test_cancel_uses_default_operator_reason(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)

        _as_operator(auth)
        response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

        assert response.status_code == 200
        assert response.json() == {
            "order_id": order_id,
            "status": "cancelled",
            "cancel_reason": "operator_cancelled",
        }

    def test_cancel_stores_explicit_reason(self, client: TestClient, auth) -> None:
        order_id = _create(client)

        _as_operator(auth)
        response = client.post(
            f"/api/v1/orders/{order_id}/cancel", json={"reason": "fraud_suspected"}
        )

        assert response.status_code == 200
        assert response.json()["cancel_reason"] == "fraud_suspected"

    def test_cancel_rejects_invalid_bodies(self, client: TestClient, auth) -> None:
        order_id = _create(client)

        _as_operator(auth)
        assert (
            client.post(
                f"/api/v1/orders/{order_id}/cancel", json={"reason": ""}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/v1/orders/{order_id}/cancel", json={"reason": "x" * 129}
            ).status_code
            == 422
        )
        assert client.post(f"/api/v1/orders/{order_id}/cancel").status_code == 422

    def test_cancel_from_non_terminal_states(
        self, client: TestClient, auth, engine
    ) -> None:
        _as_operator(auth)
        for status in ("pending", "inventory_reserved", "payment_authorized"):
            order_id = _create(client)
            _set_status(engine, order_id, status)

            response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

            assert response.status_code == 200
            assert response.json()["status"] == "cancelled"
            assert (
                client.get(f"/api/v1/orders/{order_id}").json()["cancel_reason"]
                == "operator_cancelled"
            )

    def test_cancel_idempotent_retry_preserves_reason_and_emits_once(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)

        _as_operator(auth)
        assert (
            client.post(f"/api/v1/orders/{order_id}/cancel", json={}).status_code == 200
        )
        retry = client.post(
            f"/api/v1/orders/{order_id}/cancel", json={"reason": "second_reason"}
        )

        assert retry.status_code == 200
        assert retry.json()["cancel_reason"] == "operator_cancelled"
        assert _outbox_for(engine, order_id, "OrderCancelled") == [
            ("OrderCancelled", {"status": "cancelled", "reason": "operator_cancelled"})
        ]

    def test_cancel_confirmed_returns_409(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)
        _set_status(engine, order_id, "confirmed")

        _as_operator(auth)
        response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

        assert response.status_code == 409
        assert "detail" in response.json()
        assert client.get(f"/api/v1/orders/{order_id}").json()["status"] == "confirmed"

    def test_cancel_missing_order_returns_404(self, client: TestClient, auth) -> None:
        _as_operator(auth)

        response = client.post(f"/api/v1/orders/{uuid4()}/cancel", json={})

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_cancel_emits_timeline_and_outbox_once(
        self, client: TestClient, auth, engine
    ) -> None:
        order_id = _create(client)

        _as_operator(auth)
        assert (
            client.post(f"/api/v1/orders/{order_id}/cancel", json={}).status_code == 200
        )
        assert (
            client.post(f"/api/v1/orders/{order_id}/cancel", json={}).status_code == 200
        )

        timeline = client.get(f"/api/v1/orders/{order_id}/timeline")
        assert timeline.status_code == 200
        cancelled = [e for e in timeline.json() if e["event_type"] == "OrderCancelled"]
        assert len(cancelled) == 1
        assert cancelled[0]["payload"] == {
            "status": "cancelled",
            "reason": "operator_cancelled",
        }
        assert _outbox_for(engine, order_id, "OrderCancelled") == [
            ("OrderCancelled", {"status": "cancelled", "reason": "operator_cancelled"})
        ]


class TestExistingRouteCompatibility:
    def test_create_get_timeline_still_enforce_owner_or_operator(
        self, client: TestClient, auth
    ) -> None:
        order_id = _create(client)

        assert client.get(f"/api/v1/orders/{order_id}").status_code == 200
        timeline = client.get(f"/api/v1/orders/{order_id}/timeline")
        assert timeline.status_code == 200
        assert timeline.json()[0]["event_type"] == "OrderCreated"

        auth["user"] = _user(OTHER_ID)
        assert client.get(f"/api/v1/orders/{order_id}").status_code == 404
        assert client.get(f"/api/v1/orders/{order_id}/timeline").status_code == 404

        _as_operator(auth)
        assert client.get(f"/api/v1/orders/{order_id}").status_code == 200
        assert client.get(f"/api/v1/orders/{order_id}/timeline").status_code == 200
