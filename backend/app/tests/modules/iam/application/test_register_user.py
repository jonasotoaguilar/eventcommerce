"""RegisterUser use-case tests (fake repository, no secrets asserted)."""

import inspect
from datetime import timezone

import pytest
from app.modules.iam.application.passwords import verify_password
from app.modules.iam.application.register_user import register_user
from app.modules.iam.domain.entities import User, normalize_email
from app.modules.iam.domain.errors import DuplicateEmailError


class FakeUserRepository:
    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    async def get_by_email(self, normalized_email: str) -> User | None:
        return self._store.get(normalized_email)

    async def add(self, user: User) -> None:
        self._store[user.email] = user


class RaceUserRepository(FakeUserRepository):
    async def add(self, user: User) -> None:
        raise DuplicateEmailError("email already registered")


class TestNormalizeEmail:
    def test_trims_and_casefolds(self) -> None:
        assert normalize_email("  USER@Example.COM  ") == "user@example.com"

    def test_unicode_casefold(self) -> None:
        assert normalize_email("Straße@Example.COM") == "strasse@example.com"


class TestRegisterUser:
    @pytest.mark.asyncio
    async def test_registers_shopper_with_normalized_email(self) -> None:
        repo = FakeUserRepository()
        user = await register_user(repo, "  Shopper@Example.COM  ", "valid-pass-1")

        assert user.email == "shopper@example.com"
        assert user.role == "shopper"
        assert user.id is not None
        assert user.created_at.tzinfo is not None
        assert user.created_at.utcoffset() == timezone.utc.utcoffset(None)
        assert user.updated_at.tzinfo is not None
        assert verify_password("valid-pass-1", user.password_hash)
        assert "valid-pass-1" not in user.password_hash

    @pytest.mark.asyncio
    async def test_never_accepts_role(self) -> None:
        assert "role" not in inspect.signature(register_user).parameters

    @pytest.mark.asyncio
    async def test_password_boundaries_accepted(self) -> None:
        repo = FakeUserRepository()
        await register_user(repo, "eight@example.com", "12345678")
        await register_user(repo, "long@example.com", "x" * 128)

    @pytest.mark.asyncio
    async def test_password_boundaries_rejected(self) -> None:
        repo = FakeUserRepository()
        with pytest.raises(ValueError):
            await register_user(repo, "seven@example.com", "1234567")
        with pytest.raises(ValueError):
            await register_user(repo, "toolong@example.com", "x" * 129)

    @pytest.mark.asyncio
    async def test_duplicate_precheck_raises(self) -> None:
        repo = FakeUserRepository()
        await register_user(repo, "Taken@Example.com", "valid-pass-1")
        with pytest.raises(DuplicateEmailError):
            await register_user(repo, " taken@example.COM ", "valid-pass-2")

    @pytest.mark.asyncio
    async def test_duplicate_race_propagates(self) -> None:
        with pytest.raises(DuplicateEmailError):
            await register_user(RaceUserRepository(), "new@example.com", "valid-pass-1")
