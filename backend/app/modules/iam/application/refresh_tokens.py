"""Opaque refresh-token service: hashed storage, rotation, reuse detection.

Refresh values are high-entropy opaque strings, never JWTs. Only the
SHA-256 hash is persisted, so a database leak yields no usable tokens.
Each token belongs to a family; exchanging a token consumes it and mints
a successor in the same family, while presenting an already-consumed
token revokes the whole family. Every failure raises the same generic
``InvalidTokenError`` so callers cannot distinguish the cause.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.modules.iam.domain.entities import RefreshToken, User
from app.modules.iam.domain.errors import InvalidTokenError
from app.modules.iam.domain.repository import RefreshTokenRepository, UserRepository
from app.shared.config.settings import Settings, get_settings

_GENERIC_ERROR = "Invalid or expired token"


def mint_refresh_token() -> str:
    """Return a fresh high-entropy opaque refresh value."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(value: str) -> str:
    """Return the SHA-256 hex digest persisted for a refresh value."""
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def issue_refresh_token(
    repository: RefreshTokenRepository,
    user_id: UUID,
    settings: Settings | None = None,
) -> str:
    """Open a new refresh family for a user; return the plaintext value."""
    resolved = settings or get_settings()
    value = mint_refresh_token()
    now = _now()
    await repository.add(
        RefreshToken(
            id=uuid4(),
            user_id=user_id,
            family_id=uuid4(),
            token_hash=hash_refresh_token(value),
            created_at=now,
            expires_at=now + timedelta(days=resolved.refresh_token_expires_days),
        )
    )
    return value


async def rotate_refresh_token(
    users: UserRepository,
    repository: RefreshTokenRepository,
    raw_token: str,
) -> tuple[User, str]:
    """Exchange one refresh token for its successor in the same family.

    Atomically consumes the presented token before minting its successor
    and returns the owning user plus the new plaintext value. Losing the
    consume race means another request spent this token first, so the
    family is revoked before failing, just like a sequential replay.
    """
    candidate = raw_token.strip()
    if not candidate:
        raise InvalidTokenError(_GENERIC_ERROR)
    stored = await repository.get_by_hash(hash_refresh_token(candidate))
    if stored is None:
        raise InvalidTokenError(_GENERIC_ERROR)
    if stored.revoked_at is not None:
        raise InvalidTokenError(_GENERIC_ERROR)
    if stored.expires_at <= _now():
        raise InvalidTokenError(_GENERIC_ERROR)
    if stored.consumed_at is not None:
        await repository.revoke_family(stored.family_id, _now())
        raise InvalidTokenError(_GENERIC_ERROR)
    user = await users.get_by_id(stored.user_id)
    if user is None:
        raise InvalidTokenError(_GENERIC_ERROR)
    now = _now()
    if not await repository.consume(stored.id, now):
        await repository.revoke_family(stored.family_id, _now())
        raise InvalidTokenError(_GENERIC_ERROR)
    successor = mint_refresh_token()
    await repository.add(
        RefreshToken(
            id=uuid4(),
            user_id=stored.user_id,
            family_id=stored.family_id,
            token_hash=hash_refresh_token(successor),
            created_at=now,
            expires_at=stored.expires_at,
        )
    )
    return user, successor
