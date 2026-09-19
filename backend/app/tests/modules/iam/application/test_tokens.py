"""JWT token service tests (no token/secret values asserted or logged)."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from app.modules.iam.application.tokens import issue_token, verify_token
from app.modules.iam.domain.errors import InvalidTokenError, JwtConfigurationError
from app.shared.config.settings import Settings


def _settings(**overrides):
    base = {
        "jwt_secret": secrets.token_urlsafe(32),
        "jwt_issuer": "test-issuer",
        "jwt_audience": "test-audience",
        "jwt_expires_minutes": 30,
    }
    base.update(overrides)
    return Settings(**base)


def _mint(settings, user_id, email, role, algorithm="HS256", **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": email,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "purpose": "access",
    }
    claims.update(overrides)
    return jwt.encode(claims, settings.jwt_secret, algorithm=algorithm)


def _identity():
    return uuid4(), "user@example.com", "shopper"


class TestIssueToken:
    def test_roundtrip_returns_current_user(self):
        settings = _settings()
        user_id, email, role = _identity()

        current = verify_token(
            issue_token(user_id, email, role, settings=settings), settings=settings
        )

        assert str(current.user_id) == str(user_id)
        assert (current.email, current.role) == (email, role)

    @pytest.mark.parametrize("field", ["jwt_secret", "jwt_issuer", "jwt_audience"])
    def test_blank_setting_fails_closed_on_issue(self, field):
        user_id, email, role = _identity()
        with pytest.raises(JwtConfigurationError):
            issue_token(user_id, email, role, settings=_settings(**{field: "  "}))


class TestVerifyToken:
    def test_wrong_algorithm_rejected(self):
        settings = _settings()
        user_id, email, role = _identity()
        with pytest.raises(InvalidTokenError):
            verify_token(
                _mint(settings, user_id, email, role, algorithm="HS384"),
                settings=settings,
            )

    def test_wrong_issuer_or_audience_rejected(self):
        settings = _settings()
        user_id, email, role = _identity()
        token = issue_token(user_id, email, role, settings=settings)
        with pytest.raises(InvalidTokenError):
            verify_token(
                token,
                settings=_settings(
                    jwt_secret=settings.jwt_secret, jwt_issuer="other-issuer"
                ),
            )
        with pytest.raises(InvalidTokenError):
            verify_token(
                token,
                settings=_settings(
                    jwt_secret=settings.jwt_secret, jwt_audience="other-audience"
                ),
            )

    def test_wrong_purpose_rejected(self):
        settings = _settings()
        user_id, email, role = _identity()
        with pytest.raises(InvalidTokenError):
            verify_token(
                _mint(settings, user_id, email, role, purpose="refresh"),
                settings=settings,
            )

    def test_expired_token_rejected(self):
        settings = _settings()
        user_id, email, role = _identity()
        now = datetime.now(timezone.utc)
        token = _mint(
            settings,
            user_id,
            email,
            role,
            iat=now - timedelta(hours=2),
            exp=now - timedelta(hours=1),
        )
        with pytest.raises(InvalidTokenError):
            verify_token(token, settings=settings)

    def test_malformed_token_rejected(self):
        with pytest.raises(InvalidTokenError):
            verify_token("not-a-token", settings=_settings())

    def test_tampered_signature_rejected(self):
        settings = _settings()
        user_id, email, role = _identity()
        token = issue_token(user_id, email, role, settings=settings)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with pytest.raises(InvalidTokenError):
            verify_token(tampered, settings=settings)

    def test_blank_secret_fails_closed_on_verify(self):
        settings = _settings()
        user_id, email, role = _identity()
        token = issue_token(user_id, email, role, settings=settings)
        with pytest.raises(JwtConfigurationError):
            verify_token(token, settings=_settings(jwt_secret=""))

    def test_error_message_is_generic(self):
        settings = _settings()
        with pytest.raises(InvalidTokenError) as exc:
            verify_token("not-a-token", settings=settings)
        assert str(exc.value) == "Invalid or expired token"
