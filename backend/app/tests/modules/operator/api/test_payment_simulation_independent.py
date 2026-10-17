"""Independent U3 probes. Real JWTs, not get_current_user overrides."""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.checkout.api.schemas import MAX_AMOUNT
from app.modules.iam.application.tokens import issue_token
from app.modules.payments.domain.policy import is_payment_approved, payment_digest_byte
from app.shared.config import get_settings
from app.shared.db.session import get_db_session

PATH = "/api/v1/operator/payments/simulation"


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setenv(
        "EVENTCOMMERCE_JWT_SECRET", "verifier-secret-verifier-secret-verifier"
    )
    monkeypatch.setenv("EVENTCOMMERCE_JWT_ISSUER", "verifier")
    monkeypatch.setenv("EVENTCOMMERCE_JWT_AUDIENCE", "verifier")
    get_settings.cache_clear()
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _headers(role: str) -> dict[str, str]:
    raw = issue_token(uuid4(), f"{role}@example.com", role, settings=get_settings())
    return {"Authorization": f"Bearer {raw}"}


def _params(**overrides: str) -> dict[str, str]:
    base = {"order_id": str(UUID(int=7)), "amount": "42.50", "currency": "USD"}
    base.update(overrides)
    return base


async def _digest(engine) -> str:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        tables = (
            (
                await session.execute(
                    text(
                        "select tablename from pg_tables "
                        "where schemaname='public' order by 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        parts: list[str] = []
        for table in tables:
            digest = (
                await session.execute(
                    text(
                        "select md5(coalesce(string_agg(t::text, '|' order by t::text), '')) "
                        f"from (select {table}.*::text as t from {table}) s"
                    )
                )
            ).scalar_one()
            parts.append(f"{table}:{digest}")
        return "|".join(parts)


def test_boundaries_match_policy(client: TestClient) -> None:
    headers = _headers("operator")
    approved = next(
        UUID(int=i)
        for i in range(1, 30)
        if is_payment_approved(str(UUID(int=i)), Decimal("2.01"), "USD")
    )
    rejected = next(
        UUID(int=i)
        for i in range(1, 30)
        if not is_payment_approved(str(UUID(int=i)), Decimal("9.99"), "EUR")
    )
    cases = [
        (approved, Decimal("2.01"), "USD"),
        (rejected, Decimal("9.99"), "eur"),
        (UUID(int=7), MAX_AMOUNT, "USD"),
        (UUID(int=7), Decimal("0.01"), "USD"),
    ]
    for order_id, amount, currency in cases:
        params = {
            "order_id": str(order_id),
            "amount": format(amount, "f"),
            "currency": currency,
        }
        response = client.get(PATH, params=params, headers=headers)
        assert response.status_code == 200
        body = response.json()
        norm = currency.upper()
        assert body["currency"] == norm
        assert Decimal(body["amount"]) == amount
        assert body["approved"] is is_payment_approved(str(order_id), amount, norm)
        assert body["digest_byte"] == payment_digest_byte(str(order_id), amount, norm)
        again = client.get(PATH, params=params, headers=headers)
        assert again.json() == body

    over = client.get(
        PATH,
        params=_params(amount=format(MAX_AMOUNT + Decimal("0.01"), "f")),
        headers=headers,
    )
    assert over.status_code == 422


@pytest.mark.parametrize("currency", ["USA1", "US", "USDD", ""])
def test_invalid_currency_422(client: TestClient, currency: str) -> None:
    response = client.get(
        PATH, params=_params(currency=currency), headers=_headers("operator")
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.parametrize("amount", ["0", "0.00", "-1.00"])
def test_non_positive_amount_422(client: TestClient, amount: str) -> None:
    response = client.get(
        PATH, params=_params(amount=amount), headers=_headers("operator")
    )
    assert response.status_code == 422


def test_auth_and_storage(client: TestClient, engine) -> None:
    params = _params()
    assert client.get(PATH, params=params).status_code == 401
    assert (
        client.get(PATH, params=params, headers=_headers("shopper")).status_code == 403
    )
    assert (
        client.get(
            PATH, params=params, headers={"Authorization": "Bearer not-a-jwt"}
        ).status_code
        == 401
    )
    before = asyncio.run(_digest(engine))
    allowed = client.get(PATH, params=params, headers=_headers("operator"))
    assert allowed.status_code == 200
    assert asyncio.run(_digest(engine)) == before
