"""IAM rate-limit tests: 429 with Retry-After on register/login.

Mirrors the fixtures in test_routes.py (engine-backed client with the same
monkeypatching pattern) and seeds a tight limiter on the app instance with an
injected clock, so no test sleeps.
"""

import secrets

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api import dependencies as iam_dependencies
from app.modules.iam.api import rate_limit as rate_limit_module
from app.modules.iam.api.rate_limit import RateLimiter
from app.modules.iam.api.schemas import LoginRequest, RegisterRequest
from app.modules.iam.application import tokens as iam_tokens
from app.modules.iam.infrastructure import models as _iam_models  # noqa: F401
from app.shared.config.settings import Settings
from app.shared.db.session import get_db_session

assert _iam_models is not None

LOGIN_LIMIT = 3
LOGIN_HOST_LIMIT = 60
REGISTER_LIMIT = 3
WINDOW = 60.0
NOW = 1_000.0


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


@pytest.fixture
def clock(client: TestClient) -> list[float]:
    """Seed tight per-app limiters driven by a mutable clock; return the box."""
    box = [NOW]
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.login_limiter = RateLimiter(LOGIN_LIMIT, WINDOW, clock=lambda: box[0])
    app.state.register_limiter = RateLimiter(
        REGISTER_LIMIT, WINDOW, clock=lambda: box[0]
    )
    app.state.login_host_limiter = RateLimiter(
        LOGIN_HOST_LIMIT, WINDOW, clock=lambda: box[0]
    )
    return box


def _login_host_limiter(client: TestClient) -> RateLimiter:
    app = client.app
    assert isinstance(app, FastAPI)
    limiter = app.state.login_host_limiter
    assert isinstance(limiter, RateLimiter)
    return limiter


def _login(client: TestClient, email: str, password: str = "valid-pass-1"):
    return client.post("/api/v1/iam/login", json={"email": email, "password": password})


def _register(client: TestClient, email: str, password: str = "valid-pass-1"):
    return client.post(
        "/api/v1/iam/register", json={"email": email, "password": password}
    )


def _request(app, host: str | None) -> Request:
    scope = {"type": "http", "method": "POST", "headers": [], "app": app}
    if host is not None:
        scope["client"] = (host, 50000)
    return Request(scope)


class TestLoginRateLimit:
    def test_rejects_after_configured_attempts(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "brute@example.com").status_code == 401

        response = _login(client, "brute@example.com")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(int(WINDOW))

    def test_retry_after_matches_window_actually_consumed(
        self, client: TestClient, clock: list[float]
    ) -> None:
        assert _login(client, "slow@example.com").status_code == 401
        clock[0] += 30.0
        assert _login(client, "slow@example.com").status_code == 401
        assert _login(client, "slow@example.com").status_code == 401

        response = _login(client, "slow@example.com")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "30"

    def test_window_slides_with_clock(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "patient@example.com").status_code == 401
        assert _login(client, "patient@example.com").status_code == 429

        clock[0] += WINDOW + 1.0

        assert _login(client, "patient@example.com").status_code == 401

    def test_different_email_from_same_host_keeps_own_budget(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "first@example.com").status_code == 401
        assert _login(client, "first@example.com").status_code == 429

        assert _login(client, "second@example.com").status_code == 401

    @pytest.mark.asyncio
    async def test_different_host_keeps_own_budget(
        self, client: TestClient, clock: list[float]
    ) -> None:
        body = LoginRequest(email="same@example.com", password="valid-pass-1")
        for _ in range(LOGIN_LIMIT):
            await rate_limit_module.enforce_login_rate_limit(
                _request(client.app, "host-a"), body
            )
        with pytest.raises(HTTPException) as blocked:
            await rate_limit_module.enforce_login_rate_limit(
                _request(client.app, "host-a"), body
            )

        assert blocked.value.status_code == 429
        await rate_limit_module.enforce_login_rate_limit(
            _request(client.app, "host-b"), body
        )

    def test_email_case_does_not_split_budget(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "Case@Example.com").status_code == 401

        assert _login(client, "case@example.com").status_code == 429

    def test_rejection_hides_account_existence(
        self, client: TestClient, clock: list[float]
    ) -> None:
        assert _register(client, "victim@example.com").status_code == 201
        for _ in range(LOGIN_LIMIT):
            assert (
                _login(client, "victim@example.com", "wrong-pass-1").status_code == 401
            )
        blocked_known = _login(client, "victim@example.com", "wrong-pass-1")
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "ghost@example.com").status_code == 401
        blocked_unknown = _login(client, "ghost@example.com")

        assert blocked_known.status_code == 429
        assert blocked_unknown.status_code == 429
        assert blocked_known.json()["detail"] == blocked_unknown.json()["detail"] != ""
        assert "victim@example.com" not in blocked_known.json()["detail"]
        assert "ghost@example.com" not in blocked_unknown.json()["detail"]


class TestLimiterMemory:
    def test_fully_expired_key_is_released(
        self, client: TestClient, clock: list[float]
    ) -> None:
        box = clock
        limiter = RateLimiter(LOGIN_LIMIT, WINDOW, clock=lambda: box[0])

        assert limiter.tracked_key_count == 0
        limiter.check_and_record("stale@example.com")
        assert limiter.tracked_key_count == 1

        box[0] += WINDOW + 1.0

        assert limiter.tracked_key_count == 0

    def test_live_keys_stay_tracked(
        self, client: TestClient, clock: list[float]
    ) -> None:
        box = clock
        limiter = RateLimiter(LOGIN_LIMIT, WINDOW, clock=lambda: box[0])
        limiter.check_and_record("first@example.com")
        box[0] += WINDOW / 2.0
        limiter.check_and_record("second@example.com")

        assert limiter.tracked_key_count == 2

        box[0] += WINDOW / 2.0 + 1.0

        assert limiter.tracked_key_count == 1


class TestLoginHostCeiling:
    def test_spray_across_many_accounts_is_rejected(
        self, client: TestClient, clock: list[float]
    ) -> None:
        _login_host_limiter(client).max_attempts = 5
        for i in range(5):
            assert _login(client, f"spray-{i}@example.com").status_code == 401

        response = _login(client, "spray-final@example.com")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(int(WINDOW))
        assert "spray-final@example.com" not in response.json()["detail"]

    def test_single_account_hits_own_budget_first(
        self, client: TestClient, clock: list[float]
    ) -> None:
        _login_host_limiter(client).max_attempts = 5
        for _ in range(LOGIN_LIMIT):
            assert _login(client, "single@example.com").status_code == 401

        response = _login(client, "single@example.com")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(int(WINDOW))

    def test_host_rejection_hides_account_existence(
        self, client: TestClient, clock: list[float]
    ) -> None:
        _login_host_limiter(client).max_attempts = 2
        assert _register(client, "host-victim@example.com").status_code == 201
        assert _login(client, "filler-0@example.com").status_code == 401
        assert _login(client, "filler-1@example.com").status_code == 401

        blocked_known = _login(client, "host-victim@example.com")
        blocked_unknown = _login(client, "host-ghost@example.com")

        assert blocked_known.status_code == 429
        assert blocked_unknown.status_code == 429
        assert blocked_known.json()["detail"] == blocked_unknown.json()["detail"]
        assert "host-victim@example.com" not in blocked_known.json()["detail"]


class TestRegisterRateLimit:
    def test_rejects_after_configured_attempts(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for i in range(REGISTER_LIMIT):
            assert _register(client, f"new-{i}@example.com").status_code == 201

        response = _register(client, "one-too-many@example.com")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(int(WINDOW))

    def test_window_slides_with_clock(
        self, client: TestClient, clock: list[float]
    ) -> None:
        for i in range(REGISTER_LIMIT):
            assert _register(client, f"slot-{i}@example.com").status_code == 201
        assert _register(client, "blocked@example.com").status_code == 429

        clock[0] += WINDOW + 1.0

        assert _register(client, "fresh@example.com").status_code == 201

    @pytest.mark.asyncio
    async def test_missing_client_falls_back_to_shared_bucket(
        self, client: TestClient, clock: list[float]
    ) -> None:
        body = RegisterRequest(email="nobody@example.com", password="valid-pass-1")
        for _ in range(REGISTER_LIMIT):
            await rate_limit_module.enforce_register_rate_limit(
                _request(client.app, None), body
            )

        with pytest.raises(HTTPException) as blocked:
            await rate_limit_module.enforce_register_rate_limit(
                _request(client.app, None), body
            )

        assert blocked.value.status_code == 429
        assert blocked.value.headers is not None
        assert blocked.value.headers["Retry-After"] == str(int(WINDOW))

    def test_rejection_hides_account_existence(
        self, client: TestClient, clock: list[float]
    ) -> None:
        assert _register(client, "taken@example.com").status_code == 201
        for i in range(REGISTER_LIMIT - 1):
            assert _register(client, f"filler-{i}@example.com").status_code == 201

        blocked_taken = _register(client, "taken@example.com")
        blocked_fresh = _register(client, "fresh@example.com")

        assert blocked_taken.status_code == 429
        assert blocked_fresh.status_code == 429
        assert blocked_taken.json()["detail"] == blocked_fresh.json()["detail"] != ""
        assert "taken@example.com" not in blocked_taken.json()["detail"]
