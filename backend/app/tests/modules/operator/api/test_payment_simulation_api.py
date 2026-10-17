"""Operator payment-simulation API tests (U3).

``GET /api/v1/operator/payments/simulation`` is operator-only and
evaluates the delivered payments policy without touching storage.
"""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.checkout.api.schemas import MAX_AMOUNT
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.payments.domain.policy import (
    APPROVAL_THRESHOLD,
    is_payment_approved,
    payment_digest_byte,
)
from app.shared.db.session import get_db_session

OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")
SHOPPER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _user(user_id: UUID, role: str = "shopper") -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(OPERATOR_ID, role="operator")}


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


def _find_inputs() -> tuple[tuple[UUID, Decimal], tuple[UUID, Decimal]]:
    approved: tuple[UUID, Decimal] | None = None
    rejected: tuple[UUID, Decimal] | None = None
    candidate = 1
    while approved is None or rejected is None:
        order_id = UUID(int=candidate)
        amount = Decimal(candidate) + Decimal("0.99")
        if is_payment_approved(str(order_id), amount, "USD"):
            if approved is None:
                approved = (order_id, amount)
        elif rejected is None:
            rejected = (order_id, amount)
        candidate += 1
    assert approved is not None and rejected is not None
    return approved, rejected


async def _digest(engine) -> str:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        return (
            await session.execute(
                text(
                    "select md5(coalesce(string_agg(t, '|' order by t), '')) from ("
                    " select row(o.*)::text as t from orders o"
                    " union all select row(i.*)::text from order_items i"
                    " union all select row(p.*)::text from payments p) s"
                )
            )
        ).scalar_one()


class TestPaymentSimulation:
    def test_identical_requests_return_identical_output(
        self, client: TestClient
    ) -> None:
        params = {
            "order_id": str(UUID(int=7)),
            "amount": "42.50",
            "currency": "USD",
        }

        first = client.get("/api/v1/operator/payments/simulation", params=params)
        second = client.get("/api/v1/operator/payments/simulation", params=params)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_approved_input_matches_policy(self, client: TestClient) -> None:
        (order_id, amount), _ = _find_inputs()

        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(order_id),
                "amount": str(amount),
                "currency": "USD",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["order_id"] == str(order_id)
        assert Decimal(body["amount"]) == amount
        assert body["currency"] == "USD"
        assert body["approved"] is True
        assert body["digest_byte"] == payment_digest_byte(str(order_id), amount, "USD")
        assert body["approval_threshold"] == APPROVAL_THRESHOLD
        assert set(body) == {
            "order_id",
            "amount",
            "currency",
            "approved",
            "digest_byte",
            "approval_threshold",
        }

    def test_rejected_input_matches_policy(self, client: TestClient) -> None:
        _, (order_id, amount) = _find_inputs()

        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(order_id),
                "amount": str(amount),
                "currency": "USD",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["approved"] is False
        assert body["digest_byte"] == payment_digest_byte(str(order_id), amount, "USD")
        assert body["approval_threshold"] == APPROVAL_THRESHOLD

    def test_anonymous_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": "42.50",
                "currency": "USD",
            },
        )

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_shopper_returns_403(self, client: TestClient, auth) -> None:
        auth["user"] = _user(SHOPPER_ID)

        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": "42.50",
                "currency": "USD",
            },
        )

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_malformed_order_id_returns_422(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={"order_id": "not-a-uuid", "amount": "42.50", "currency": "USD"},
        )

        assert response.status_code == 422

    def test_missing_params_return_422(self, client: TestClient) -> None:
        assert (
            client.get(
                "/api/v1/operator/payments/simulation",
                params={"amount": "42.50", "currency": "USD"},
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/operator/payments/simulation",
                params={"order_id": str(UUID(int=7)), "currency": "USD"},
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/operator/payments/simulation",
                params={"order_id": str(UUID(int=7)), "amount": "42.50"},
            ).status_code
            == 422
        )

    @pytest.mark.parametrize("amount", ["0", "0.00", "-1.00"])
    def test_non_positive_amount_returns_422(
        self, client: TestClient, amount: str
    ) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": amount,
                "currency": "USD",
            },
        )

        assert response.status_code == 422

    def test_over_max_amount_returns_422(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": str(MAX_AMOUNT + Decimal("0.01")),
                "currency": "USD",
            },
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("currency", ["US", "USDD", "U1!"])
    def test_unsupported_currency_returns_422(
        self, client: TestClient, currency: str
    ) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": "42.50",
                "currency": currency,
            },
        )

        assert response.status_code == 422

    def test_call_writes_nothing(self, client: TestClient, engine) -> None:
        params = {
            "order_id": str(UUID(int=7)),
            "amount": "42.50",
            "currency": "USD",
        }
        before = asyncio.run(_digest(engine))

        response = client.get("/api/v1/operator/payments/simulation", params=params)

        assert response.status_code == 200
        assert asyncio.run(_digest(engine)) == before

    def test_lower_case_currency_normalizes_like_checkout(
        self, client: TestClient
    ) -> None:
        base = {"order_id": str(UUID(int=7)), "amount": "42.50"}

        upper = client.get(
            "/api/v1/operator/payments/simulation",
            params={**base, "currency": "USD"},
        )
        lower = client.get(
            "/api/v1/operator/payments/simulation",
            params={**base, "currency": "usd"},
        )

        assert lower.status_code == 200
        assert lower.json() == upper.json()
        assert lower.json()["currency"] == "USD"

    @pytest.mark.parametrize("amount", ["1.005", "10.000", "0.001"])
    def test_more_than_two_decimals_returns_422(
        self, client: TestClient, amount: str
    ) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": amount,
                "currency": "USD",
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "amount must have at most two decimal places"
        )

    @pytest.mark.parametrize("amount", ["2.5", "2.50", "42"])
    def test_two_decimals_or_fewer_are_accepted(
        self, client: TestClient, amount: str
    ) -> None:
        response = client.get(
            "/api/v1/operator/payments/simulation",
            params={
                "order_id": str(UUID(int=7)),
                "amount": amount,
                "currency": "USD",
            },
        )

        assert response.status_code == 200
