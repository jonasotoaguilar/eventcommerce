"""User repository protocol (infrastructure implements later)."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.iam.domain.entities import RefreshToken, User


class UserRepository(Protocol):
    async def get_by_email(self, normalized_email: str) -> User | None:
        """Return the user for a normalized email, or None when unknown."""
        ...

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user for an id, or None when unknown."""
        ...

    async def add(self, user: User) -> None:
        """Persist a new user; may raise DuplicateEmailError on a DB race."""
        ...


class RefreshTokenRepository(Protocol):
    async def add(self, token: RefreshToken) -> None:
        """Persist a newly issued refresh token."""
        ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Return the row for a token hash, or None when unknown."""
        ...

    async def consume(self, token_id: UUID, at: datetime) -> bool:
        """Atomically consume a fresh token.

        False when the token was already consumed or its family was revoked,
        so a revocation racing this spend cannot be spent past.
        """
        ...

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        """Revoke every unrevoked token sharing a family id.

        Must not return before an in-flight rotation of the family finishes,
        so a successor inserted by one of them is revoked too.
        """
        ...
