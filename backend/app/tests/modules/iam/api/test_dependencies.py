"""IAM FastAPI dependency tests (direct calls, no TestClient, no secrets logged)."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.modules.iam.api import dependencies as deps
from app.modules.iam.api.dependencies import get_current_user, require_roles
from app.modules.iam.application.tokens import issue_token
from app.shared.config.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        jwt_secret=secrets.token_urlsafe(32), jwt_issuer="i", jwt_audience="a"
    )


@pytest.fixture(autouse=True)
def _patched_settings(monkeypatch, settings):
    monkeypatch.setattr(deps, "get_settings", lambda: settings)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _expired(settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "user_id": str(uuid4()),
            "email": "user@example.com",
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


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(None)
        assert exc.value.status_code == 401 and exc.value.detail

    @pytest.mark.asyncio
    async def test_malformed_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_credentials("not-a-token"))
        assert exc.value.status_code == 401 and exc.value.detail

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, settings):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_credentials(_expired(settings)))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_current_user(self, settings):
        user_id = uuid4()
        token = issue_token(user_id, "user@example.com", "shopper", settings=settings)

        current = await get_current_user(_credentials(token))

        assert str(current.user_id) == str(user_id)
        assert (current.email, current.role) == ("user@example.com", "shopper")


class TestRequireRoles:
    @pytest.mark.asyncio
    async def test_matching_role_allowed(self, settings):
        token = issue_token(uuid4(), "ops@example.com", "operator", settings=settings)
        current = await get_current_user(_credentials(token))

        assert (await require_roles("operator")(current)).role == "operator"

    @pytest.mark.asyncio
    async def test_wrong_role_raises_403_not_401(self, settings):
        token = issue_token(uuid4(), "user@example.com", "shopper", settings=settings)
        current = await get_current_user(_credentials(token))
        with pytest.raises(HTTPException) as exc:
            await require_roles("operator")(current)
        assert exc.value.status_code == 403 and exc.value.detail
