"""JWT access-token service (maintained PyJWT, HS256 allowlist only)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from app.modules.iam.domain.errors import InvalidTokenError, JwtConfigurationError
from app.shared.config.settings import Settings, get_settings

_ALGORITHM = "HS256"
_PURPOSE = "access"
_GENERIC_ERROR = "Invalid or expired token"


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    email: str
    role: str


def _require_config(settings: Settings) -> Settings:
    if not settings.jwt_secret.strip():
        raise JwtConfigurationError("JWT secret is not configured")
    if not settings.jwt_issuer.strip():
        raise JwtConfigurationError("JWT issuer is not configured")
    if not settings.jwt_audience.strip():
        raise JwtConfigurationError("JWT audience is not configured")
    return settings


def issue_token(
    user_id: UUID | str,
    email: str,
    role: str,
    settings: Settings | None = None,
) -> str:
    """Issue a signed 30-minute (or configured) access token."""
    resolved = _require_config(settings or get_settings())
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "user_id": str(user_id),
            "email": email,
            "role": role,
            "iss": resolved.jwt_issuer,
            "aud": resolved.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=resolved.jwt_expires_minutes),
            "purpose": _PURPOSE,
        },
        resolved.jwt_secret,
        algorithm=_ALGORITHM,
    )


def verify_token(token: str, settings: Settings | None = None) -> CurrentUser:
    """Verify signature/algorithm/issuer/audience/expiry/purpose; fail closed."""
    resolved = _require_config(settings or get_settings())
    try:
        claims = jwt.decode(
            token,
            resolved.jwt_secret,
            algorithms=[_ALGORITHM],
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        raise InvalidTokenError(_GENERIC_ERROR) from exc
    if claims.get("purpose") != _PURPOSE:
        raise InvalidTokenError(_GENERIC_ERROR)
    try:
        return CurrentUser(
            user_id=UUID(str(claims["sub"])),
            email=str(claims["email"]),
            role=str(claims["role"]),
        )
    except Exception as exc:
        raise InvalidTokenError(_GENERIC_ERROR) from exc
