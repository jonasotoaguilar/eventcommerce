"""Refresh-token service unit tests (W3/S2): opaque mint, hash, rotation rules.

Pure unit tests over in-memory repository doubles; the HTTP contract is
covered in ``api/test_refresh.py``.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from app.modules.iam.application.refresh_tokens import (
    hash_refresh_token,
    issue_refresh_token,
    mint_refresh_token,
    rotate_refresh_token,
)
from app.modules.iam.domain.entities import RefreshToken, User
from app.modules.iam.domain.errors import InvalidTokenError
from app.shared.config.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "jwt_secret": secrets.token_urlsafe(32),
        "jwt_issuer": "test-issuer",
        "jwt_audience": "test-audience",
        "refresh_token_expires_days": 14,
    }
    base.update(overrides)
    return Settings(**base)


def _user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email="refresh@example.com",
        password_hash="hash",
        role="shopper",
        created_at=now,
        updated_at=now,
    )


class _MemoryUsers:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def get_by_email(self, normalized_email: str) -> User | None:
        return self._user

    async def get_by_id(self, user_id: UUID) -> User | None:
        if self._user is not None and self._user.id == user_id:
            return self._user
        return None

    async def add(self, user: User) -> None:
        self._user = user


class _MemoryRefreshTokens:
    def __init__(self) -> None:
        self.rows: dict[UUID, RefreshToken] = {}

    async def add(self, token: RefreshToken) -> None:
        self.rows[token.id] = token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next(
            (row for row in self.rows.values() if row.token_hash == token_hash), None
        )

    async def consume(self, token_id: UUID, at: datetime) -> bool:
        row = self.rows[token_id]
        if row.consumed_at is not None:
            return False
        row.consumed_at = at
        return True

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        for row in self.rows.values():
            if row.family_id == family_id and row.revoked_at is None:
                row.revoked_at = at


class TestMintAndHash:
    def test_minted_value_is_opaque_high_entropy(self) -> None:
        values = {mint_refresh_token() for _ in range(50)}

        assert len(values) == 50
        for value in values:
            assert "." not in value
            assert len(value) >= 43

    def test_hash_is_stable_sha256_hex(self) -> None:
        value = mint_refresh_token()

        assert hash_refresh_token(value) == hashlib.sha256(value.encode()).hexdigest()
        assert hash_refresh_token(value) == hash_refresh_token(value)
        assert hash_refresh_token(value) != value


class TestRotateRefreshToken:
    @pytest.mark.asyncio
    async def test_issue_then_rotate_returns_same_user_and_new_value(
        self,
    ) -> None:
        settings = _settings()
        user = _user()
        users, tokens = _MemoryUsers(user), _MemoryRefreshTokens()

        first = await issue_refresh_token(tokens, user.id, settings=settings)
        owner, second = await rotate_refresh_token(users, tokens, first)

        assert owner.id == user.id
        assert second != first
        consumed = await tokens.get_by_hash(hash_refresh_token(first))
        assert consumed is not None
        assert consumed.consumed_at is not None
        assert await tokens.get_by_hash(hash_refresh_token(second)) is not None

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self) -> None:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(
                _MemoryUsers(_user()),
                _MemoryRefreshTokens(),
                secrets.token_urlsafe(32),
            )

    @pytest.mark.asyncio
    async def test_blank_token_rejected(self) -> None:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(
                _MemoryUsers(_user()), _MemoryRefreshTokens(), "   "
            )

    @pytest.mark.asyncio
    async def test_replay_revokes_whole_family(self) -> None:
        settings = _settings()
        user = _user()
        users, tokens = _MemoryUsers(user), _MemoryRefreshTokens()
        first = await issue_refresh_token(tokens, user.id, settings=settings)
        _, second = await rotate_refresh_token(users, tokens, first)

        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(users, tokens, first)

        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(users, tokens, second)
        for row in tokens.rows.values():
            assert row.revoked_at is not None

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self) -> None:
        settings = _settings()
        user = _user()
        users, tokens = _MemoryUsers(user), _MemoryRefreshTokens()
        value = await issue_refresh_token(tokens, user.id, settings=settings)
        stored = await tokens.get_by_hash(hash_refresh_token(value))
        assert stored is not None
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(users, tokens, value)

    @pytest.mark.asyncio
    async def test_token_without_owner_rejected(self) -> None:
        settings = _settings()
        tokens = _MemoryRefreshTokens()
        value = await issue_refresh_token(tokens, uuid4(), settings=settings)

        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(_MemoryUsers(None), tokens, value)
