"""U6 IAM security regression: responses never leak secrets.

Proves register/login/me success and error bodies omit password,
password_hash, secret, and token material beyond the login access_token.
Unit-level TestClient with dependency overrides; no live DB.
"""

import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app import create_app
from app.modules.iam.api import dependencies as iam_dependencies
from app.modules.iam.api.container import iam_container
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application import tokens as iam_tokens
from app.modules.iam.application.authenticate_user import (
    authenticate_user as real_authenticate,
)
from app.modules.iam.application.passwords import hash_password
from app.modules.iam.application.register_user import register_user as real_register
from app.modules.iam.application.tokens import CurrentUser
from app.modules.iam.domain.entities import User
from app.modules.iam.domain.errors import DuplicateEmailError, InvalidCredentialsError
from app.shared.config.settings import Settings
from app.shared.db.session import get_db_session

PASSWORD = "valid-pass-1"
FORBIDDEN_SUBSTRINGS = ("password_hash", "secret")


def _settings() -> Settings:
    return Settings(
        jwt_secret=secrets.token_urlsafe(32),
        jwt_issuer="iam-regression-issuer",
        jwt_audience="iam-regression-audience",
    )


class _DummySession:
    async def commit(self) -> None:
        return None


def _user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email="regression@example.com",
        password_hash=hash_password(PASSWORD),
        role="shopper",
        created_at=now,
        updated_at=now,
    )


def _client(monkeypatch, register_fn=None, authenticate_fn=None) -> FastAPI:
    settings = _settings()
    monkeypatch.setattr(iam_tokens, "get_settings", lambda: settings)
    monkeypatch.setattr(iam_dependencies, "get_settings", lambda: settings)
    app = create_app()

    async def override_get_session():
        yield _DummySession()  # type: ignore[misc]

    app.dependency_overrides[get_db_session] = override_get_session
    iam_container.user_repo.override(object())
    iam_container.register_user.override(register_fn or real_register)
    iam_container.authenticate_user.override(authenticate_fn or real_authenticate)
    return app


def _teardown(app) -> None:
    app.dependency_overrides.clear()
    iam_container.user_repo.reset_override()
    iam_container.register_user.reset_override()
    iam_container.authenticate_user.reset_override()


def _assert_no_secrets(body: object, raw: str) -> None:
    """Assert no secret values or hashes leak; the generic word in detail is OK."""
    lowered = raw.lower()
    for marker in FORBIDDEN_SUBSTRINGS:
        assert marker not in lowered, f"leaked marker: {marker}"
    assert PASSWORD not in raw
    if isinstance(body, dict):
        keys = {k.lower() for k in body.keys()}
        assert "password" not in keys
        assert "password_hash" not in keys
        assert "secret" not in keys
        for value in body.values():
            if isinstance(value, str):
                assert value != PASSWORD
                assert "argon2" not in value.lower()


def test_register_success_omits_secrets(monkeypatch) -> None:
    user = _user()

    async def fake_register(repository, email: str, password: str) -> User:
        assert password == PASSWORD
        return user

    app = _client(monkeypatch, register_fn=fake_register)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/iam/register",
            json={"email": "regression@example.com", "password": PASSWORD},
        )
        assert response.status_code == 201
        assert set(response.json()) == {"user_id", "email", "role"}
        _assert_no_secrets(response.json(), response.text)
    finally:
        _teardown(app)


def test_register_conflict_omits_secrets(monkeypatch) -> None:
    async def fake_register(repository, email: str, password: str) -> User:
        raise DuplicateEmailError("Email already registered")

    app = _client(monkeypatch, register_fn=fake_register)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/iam/register",
            json={"email": "taken@example.com", "password": PASSWORD},
        )
        assert response.status_code == 409
        _assert_no_secrets(response.json(), response.text)
    finally:
        _teardown(app)


def test_login_success_only_token_material_is_access_token(monkeypatch) -> None:
    user = _user()

    async def fake_authenticate(repository, email: str, password: str) -> User:
        return user

    app = _client(monkeypatch, authenticate_fn=fake_authenticate)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/iam/login",
            json={"email": "regression@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type"}
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        _assert_no_secrets(body, response.text.replace(body["access_token"], ""))
    finally:
        _teardown(app)


def test_login_failure_omits_secrets(monkeypatch) -> None:
    async def fake_authenticate(repository, email: str, password: str) -> User:
        raise InvalidCredentialsError("Invalid email or password")

    app = _client(monkeypatch, authenticate_fn=fake_authenticate)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/iam/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        assert response.status_code == 401
        _assert_no_secrets(response.json(), response.text)
    finally:
        _teardown(app)


def test_me_success_and_failures_omit_secrets(monkeypatch) -> None:
    user = _user()
    app = _client(monkeypatch)
    current = CurrentUser(user_id=user.id, email=user.email, role=user.role)

    async def override_current_user() -> CurrentUser:
        return current

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        client = TestClient(app)
        ok = client.get("/api/v1/iam/me", headers={"Authorization": "Bearer x"})
        assert ok.status_code == 200
        assert set(ok.json()) == {"user_id", "email", "role"}
        _assert_no_secrets(ok.json(), ok.text)

        app.dependency_overrides.pop(get_current_user)
        missing = client.get("/api/v1/iam/me")
        assert missing.status_code == 401
        _assert_no_secrets(missing.json(), missing.text)

        bad = client.get(
            "/api/v1/iam/me", headers={"Authorization": "Bearer not-a-token"}
        )
        assert bad.status_code == 401
        _assert_no_secrets(bad.json(), bad.text)
    finally:
        _teardown(app)
