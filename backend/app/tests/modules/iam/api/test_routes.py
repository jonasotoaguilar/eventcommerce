"""IAM route tests: register/login/me over real HTTP against disposable PG."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api import dependencies as iam_dependencies
from app.modules.iam.application import tokens as iam_tokens
from app.modules.iam.infrastructure import models as _iam_models  # noqa: F401
from app.shared.config.settings import Settings
from app.shared.db.session import get_db_session

assert _iam_models is not None


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret=secrets.token_urlsafe(32),
        jwt_issuer="iam-test-issuer",
        jwt_audience="iam-test-audience",
    )


@pytest.fixture
def client(engine, monkeypatch, test_settings) -> TestClient:
    monkeypatch.setattr(iam_tokens, "get_settings", lambda: test_settings)
    monkeypatch.setattr(iam_dependencies, "get_settings", lambda: test_settings)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "valid-pass-1"):
    return client.post(
        "/api/v1/iam/register", json={"email": email, "password": password}
    )


def _expired_token(settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "user_id": str(uuid4()),
            "email": "gone@example.com",
            "role": "shopper",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "purpose": "access",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


class TestRegister:
    def test_returns_201_with_user_shape(self, client: TestClient) -> None:
        response = _register(client, "Shopper@Example.com")

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "shopper@example.com"
        assert data["role"] == "shopper"
        assert data["user_id"]

    def test_duplicate_returns_409(self, client: TestClient) -> None:
        assert _register(client, "taken@example.com").status_code == 201

        response = _register(client, "taken@example.com")

        assert response.status_code == 409
        assert response.json()["detail"]

    def test_duplicate_case_variant_returns_409(self, client: TestClient) -> None:
        assert _register(client, "Taken@Example.com").status_code == 201

        assert _register(client, " taken@example.COM ").status_code == 409

    def test_invalid_email_returns_422(self, client: TestClient) -> None:
        assert _register(client, "not-an-email").status_code == 422

    def test_short_password_returns_422(self, client: TestClient) -> None:
        assert _register(client, "short@example.com", "1234567").status_code == 422

    def test_long_password_returns_422(self, client: TestClient) -> None:
        assert _register(client, "long@example.com", "x" * 129).status_code == 422


class TestLogin:
    def test_returns_bearer_token(self, client: TestClient) -> None:
        _register(client, "login@example.com")

        response = client.post(
            "/api/v1/iam/login",
            json={"email": "login@example.com", "password": "valid-pass-1"},
        )

        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"
        assert response.json()["access_token"]

    def test_unknown_and_wrong_password_share_generic_401(
        self, client: TestClient
    ) -> None:
        _register(client, "victim@example.com")

        unknown = client.post(
            "/api/v1/iam/login",
            json={"email": "nobody@example.com", "password": "valid-pass-1"},
        )
        wrong = client.post(
            "/api/v1/iam/login",
            json={"email": "victim@example.com", "password": "wrong-pass-1"},
        )

        assert unknown.status_code == 401
        assert wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_invalid_email_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/iam/login",
            json={"email": "not-an-email", "password": "valid-pass-1"},
        )

        assert response.status_code == 422


class TestMe:
    def _token(self, client: TestClient) -> str:
        _register(client, "me@example.com")
        response = client.post(
            "/api/v1/iam/login",
            json={"email": "me@example.com", "password": "valid-pass-1"},
        )
        return response.json()["access_token"]

    def test_returns_caller(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/iam/me", headers={"Authorization": f"Bearer {self._token(client)}"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "user_id": response.json()["user_id"],
            "email": "me@example.com",
            "role": "shopper",
        }

    def test_missing_token_returns_401(self, client: TestClient) -> None:
        assert client.get("/api/v1/iam/me").status_code == 401

    def test_malformed_token_returns_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/iam/me", headers={"Authorization": "Bearer not-a-token"}
        )

        assert response.status_code == 401

    def test_tampered_token_returns_401(self, client: TestClient) -> None:
        token = self._token(client)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        response = client.get(
            "/api/v1/iam/me", headers={"Authorization": f"Bearer {tampered}"}
        )

        assert response.status_code == 401

    def test_expired_token_returns_401(
        self, client: TestClient, test_settings: Settings
    ) -> None:
        response = client.get(
            "/api/v1/iam/me",
            headers={"Authorization": f"Bearer {_expired_token(test_settings)}"},
        )

        assert response.status_code == 401
