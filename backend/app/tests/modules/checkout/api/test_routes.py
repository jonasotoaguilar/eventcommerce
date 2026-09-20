"""RED tests for the S3c2b checkout routes (task 3.16).

Covers the outcome mapping of ``POST /api/v1/checkout`` — 201 success,
422 validation (body and Idempotency-Key header), 409 conflict, 500
internal with rollback — plus the header-to-core mapping contract and
the route-level structured logs (``checkout_started`` / ``checkout_rolled_back``,
key-hash prefix only, never the raw key).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Generator
from uuid import UUID

import pytest
import pytest_asyncio
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app import create_app
from app.modules.checkout.api.container import checkout_container
from app.modules.checkout.api.schemas import CheckoutRequest
from app.modules.checkout.application.checkout import CheckoutResult
from app.modules.checkout.application.errors import IdempotencyConflictError
from app.modules.checkout.application.helpers import hash_key
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.shared.db.session import get_db_session


class _FakeSession:
    """Minimal session stand-in recording rollbacks for the 500 path."""

    def __init__(self) -> None:
        self.rollback_calls = 0

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeCheckout:
    """Configurable stand-in for the checkout use case."""

    def __init__(self) -> None:
        self.received: list[CheckoutRequest] = []
        self.result: CheckoutResult = CheckoutResult(
            status_code=201,
            body={
                "order_id": "00000000-0000-0000-0000-000000000001",
                "status": "confirmed",
                "cancel_reason": None,
                "payment_status": "authorized",
            },
        )
        self.error: Exception | None = None

    async def execute(self, request: CheckoutRequest) -> CheckoutResult:
        self.received.append(request)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def fake_checkout() -> Generator[_FakeCheckout, None, None]:
    use_case = _FakeCheckout()
    checkout_container.checkout.override(providers.Object(use_case))
    try:
        yield use_case
    finally:
        checkout_container.checkout.reset_override()


@pytest.fixture
def fake_session() -> _FakeSession:
    return _FakeSession()


@pytest.fixture
def auth_user() -> CurrentUser:
    return CurrentUser(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="shopper@example.com",
        role="shopper",
    )


@pytest_asyncio.fixture
async def client(
    fake_checkout: _FakeCheckout,
    fake_session: _FakeSession,
    auth_user: CurrentUser,
) -> AsyncIterator[TestClient]:
    app = create_app()

    async def override_get_session() -> AsyncIterator[_FakeSession]:
        yield fake_session

    async def override_current_user() -> CurrentUser:
        return auth_user

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_current_user
    yield TestClient(app)


def _valid_body() -> dict:
    return {
        "customer_id": "cus_1",
        "items": [{"product_id": "P1", "quantity": 2}],
        "amount": "19.99",
        "currency": "USD",
    }


class TestCheckoutRouteMapping:
    def test_accepted_outcome_returns_201_with_response_body(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        response = client.post("/api/v1/checkout", json=_valid_body())

        assert response.status_code == 201
        assert response.json() == fake_checkout.result.body

    def test_conflict_outcome_maps_to_409(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        fake_checkout.error = IdempotencyConflictError(
            "Idempotency-Key was reused with a different payload"
        )

        response = client.post(
            "/api/v1/checkout", json=_valid_body(), headers={"Idempotency-Key": "k-1"}
        )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Idempotency-Key was reused with a different payload"
        )

    def test_internal_outcome_rolls_back_and_returns_500(
        self,
        client: TestClient,
        fake_checkout: _FakeCheckout,
        fake_session: _FakeSession,
    ) -> None:
        fake_checkout.error = RuntimeError("db exploded")

        response = client.post(
            "/api/v1/checkout", json=_valid_body(), headers={"Idempotency-Key": "k-2"}
        )

        assert response.status_code == 500
        assert fake_session.rollback_calls == 1

    def test_validation_errors_return_422(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        invalid_bodies = [
            {**_valid_body(), "items": [{"product_id": "P1", "quantity": 0}]},
            {**_valid_body(), "items": []},
            {**_valid_body(), "currency": "US"},
            {**_valid_body(), "amount": "19.999"},
        ]

        for body in invalid_bodies:
            response = client.post("/api/v1/checkout", json=body)
            assert response.status_code == 422, body
            assert fake_checkout.received == []

    def test_invalid_idempotency_header_returns_422(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        # Note: a non-ASCII header value (RFC 7230: header fields are
        # ASCII-only) cannot be transmitted by the HTTP client at all —
        # httpx rejects it before a request exists, so no server-side
        # vector exists for it. Visible-ASCII validation is exercised by
        # the remaining vectors.
        for header_value in ["spaced key", ""]:
            response = client.post(
                "/api/v1/checkout",
                json=_valid_body(),
                headers={"Idempotency-Key": header_value},
            )
            assert response.status_code == 422, repr(header_value)
            assert fake_checkout.received == []


class TestCheckoutRequestMapping:
    def test_idempotency_header_maps_into_core_request(
        self,
        client: TestClient,
        fake_checkout: _FakeCheckout,
        auth_user: CurrentUser,
    ) -> None:
        client.post(
            "/api/v1/checkout",
            json=_valid_body(),
            headers={"Idempotency-Key": "req-key-1"},
        )

        assert len(fake_checkout.received) == 1
        assert fake_checkout.received[0].idempotency_key == "req-key-1"
        assert fake_checkout.received[0].customer_id == str(auth_user.user_id)

    def test_missing_header_leaves_core_request_key_absent(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        client.post("/api/v1/checkout", json=_valid_body())

        assert fake_checkout.received[0].idempotency_key is None

    def test_header_is_authoritative_over_body_sent_key(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        body = {**_valid_body(), "idempotency_key": "body-key"}
        client.post(
            "/api/v1/checkout", json=body, headers={"Idempotency-Key": "header-key"}
        )

        assert fake_checkout.received[0].idempotency_key == "header-key"

    def test_body_sent_key_is_dropped_when_header_absent(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        body = {**_valid_body(), "idempotency_key": "body-key"}
        client.post("/api/v1/checkout", json=body)

        assert fake_checkout.received[0].idempotency_key is None


class TestCheckoutSubjectDerivation:
    def test_body_customer_id_is_overridden_by_subject(
        self,
        client: TestClient,
        fake_checkout: _FakeCheckout,
        auth_user: CurrentUser,
    ) -> None:
        body = {**_valid_body(), "customer_id": "attacker-chosen-id"}
        response = client.post("/api/v1/checkout", json=body)

        assert response.status_code == 201
        assert fake_checkout.received[0].customer_id == str(auth_user.user_id)

    def test_anonymous_checkout_returns_401(
        self, client: TestClient, fake_checkout: _FakeCheckout
    ) -> None:
        app = client.app
        assert isinstance(app, FastAPI)
        app.dependency_overrides.pop(get_current_user)

        response = client.post("/api/v1/checkout", json=_valid_body())

        assert response.status_code == 401
        assert fake_checkout.received == []


@pytest.fixture
def pg_auth(auth_user: CurrentUser) -> dict:
    return {"user": auth_user}


@pytest_asyncio.fixture
async def pg_client(engine, pg_auth: dict) -> AsyncIterator[TestClient]:
    """Real route + disposable PostgreSQL client for U5 checkout proofs."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    async def override_current_user() -> CurrentUser:
        return pg_auth["user"]

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_current_user
    async with session_factory() as session:
        await SqlAlchemyInventoryRepository(session).save(
            Inventory(product_id="P1", available_quantity=10, reserved_quantity=0)
        )
        await session.commit()
    yield TestClient(app)


def _pg_body(**overrides) -> dict:
    body: dict = {
        "customer_id": "attacker-chosen-id",
        "items": [{"product_id": "P1", "quantity": 2}],
        "amount": "19.99",
        "currency": "USD",
    }
    body.update(overrides)
    return body


class TestCheckoutIamBoundaryPostgres:
    def test_subject_becomes_owner_and_replay_returns_same_order(
        self, pg_client: TestClient, auth_user: CurrentUser
    ) -> None:
        headers = {"Idempotency-Key": "u5-key-1"}
        first = pg_client.post("/api/v1/checkout", json=_pg_body(), headers=headers)

        assert first.status_code == 201
        # Terminal outcome (confirmed/cancelled) depends on the payment
        # policy digest; U5 only needs a stable, subject-owned order.
        assert first.json()["status"] in ("confirmed", "cancelled")
        order_id = first.json()["order_id"]

        as_owner = pg_client.get(f"/api/v1/orders/{order_id}")
        assert as_owner.status_code == 200
        assert as_owner.json()["customer_id"] == str(auth_user.user_id)

        second = pg_client.post("/api/v1/checkout", json=_pg_body(), headers=headers)
        assert second.status_code == 201
        assert second.json()["order_id"] == order_id

    def test_cross_user_cannot_read_checkout_order(
        self, pg_client: TestClient, pg_auth: dict
    ) -> None:
        created = pg_client.post(
            "/api/v1/checkout",
            json=_pg_body(),
            headers={"Idempotency-Key": "u5-key-2"},
        )
        assert created.status_code == 201
        order_id = created.json()["order_id"]

        pg_auth["user"] = CurrentUser(
            user_id=UUID("22222222-2222-2222-2222-222222222222"),
            email="other@example.com",
            role="shopper",
        )

        assert pg_client.get(f"/api/v1/orders/{order_id}").status_code == 404

    def test_anonymous_checkout_returns_401(self, pg_client: TestClient) -> None:
        app = pg_client.app
        assert isinstance(app, FastAPI)
        app.dependency_overrides.pop(get_current_user)

        response = pg_client.post("/api/v1/checkout", json=_pg_body())

        assert response.status_code == 401


class TestCheckoutLogging:
    def test_checkout_started_logs_only_key_hash(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        client.post(
            "/api/v1/checkout",
            json=_valid_body(),
            headers={"Idempotency-Key": "secret-key"},
        )

        messages = [record.message for record in caplog.records]
        assert any("checkout_started" in message for message in messages)
        started = next(message for message in messages if "checkout_started" in message)
        assert f"key_hash={hash_key('secret-key')}" in started
        assert "secret-key" not in started

    def test_checkout_rolled_back_logs_only_key_hash(
        self,
        client: TestClient,
        fake_checkout: _FakeCheckout,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fake_checkout.error = RuntimeError("boom")
        caplog.set_level(logging.INFO)

        client.post(
            "/api/v1/checkout",
            json=_valid_body(),
            headers={"Idempotency-Key": "secret-key"},
        )

        messages = [record.message for record in caplog.records]
        assert any("checkout_rolled_back" in message for message in messages)
        rolled_back = next(
            message for message in messages if "checkout_rolled_back" in message
        )
        assert f"key_hash={hash_key('secret-key')}" in rolled_back
        assert "secret-key" not in rolled_back
