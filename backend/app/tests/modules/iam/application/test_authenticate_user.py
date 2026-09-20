"""AuthenticateUser use-case tests (fake repository, no secrets asserted)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.modules.iam.application import authenticate_user as authenticate_module
from app.modules.iam.application.authenticate_user import authenticate_user
from app.modules.iam.application.passwords import verify_password
from app.modules.iam.application.register_user import register_user
from app.modules.iam.domain.entities import User
from app.modules.iam.domain.errors import InvalidCredentialsError


class FakeUserRepository:
    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    async def get_by_email(self, normalized_email: str) -> User | None:
        return self._store.get(normalized_email)

    async def add(self, user: User) -> None:
        self._store[user.email] = user


async def _registered(repo: FakeUserRepository) -> User:
    return await register_user(repo, "user@example.com", "correct-pass-1")


class TestAuthenticateUser:
    @pytest.mark.asyncio
    async def test_success_returns_user(self) -> None:
        repo = FakeUserRepository()
        created = await _registered(repo)

        user = await authenticate_user(repo, " USER@example.com ", "correct-pass-1")

        assert user == created

    @pytest.mark.asyncio
    async def test_unknown_email_fails_generic(self) -> None:
        repo = FakeUserRepository()
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(repo, "ghost@example.com", "correct-pass-1")

    @pytest.mark.asyncio
    async def test_wrong_password_fails_generic(self) -> None:
        repo = FakeUserRepository()
        await _registered(repo)
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(repo, "user@example.com", "wrong-password")

    @pytest.mark.asyncio
    async def test_same_error_for_unknown_email_and_wrong_password(self) -> None:
        repo = FakeUserRepository()
        await _registered(repo)
        with pytest.raises(InvalidCredentialsError) as unknown_exc:
            await authenticate_user(repo, "ghost@example.com", "correct-pass-1")
        with pytest.raises(InvalidCredentialsError) as wrong_exc:
            await authenticate_user(repo, "user@example.com", "wrong-password")
        assert type(unknown_exc.value) is type(wrong_exc.value)

    @pytest.mark.asyncio
    async def test_malformed_hash_fails_closed(self) -> None:
        repo = FakeUserRepository()
        now = datetime.now(timezone.utc)
        await repo.add(
            User(
                id=uuid4(),
                email="user@example.com",
                password_hash="not-a-valid-hash",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(repo, "user@example.com", "correct-pass-1")

    @pytest.mark.asyncio
    async def test_unknown_email_still_verifies_once(self, monkeypatch) -> None:
        repo = FakeUserRepository()
        calls: list[tuple[str, str]] = []
        real_verify = verify_password

        def _spy(password: str, password_hash: str) -> bool:
            calls.append((password, password_hash))
            return real_verify(password, password_hash)

        monkeypatch.setattr(authenticate_module, "verify_password", _spy)
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(repo, "ghost@example.com", "any-password-1")

        assert len(calls) == 1
        attempt_password, attempt_hash = calls[0]
        assert attempt_password == "any-password-1"
        assert "any-password-1" not in attempt_hash
        assert isinstance(real_verify("any-password-1", attempt_hash), bool)
