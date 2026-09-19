"""User repository protocol (infrastructure implements later)."""

from typing import Protocol

from app.modules.iam.domain.entities import User


class UserRepository(Protocol):
    async def get_by_email(self, normalized_email: str) -> User | None:
        """Return the user for a normalized email, or None when unknown."""
        ...

    async def add(self, user: User) -> None:
        """Persist a new user; may raise DuplicateEmailError on a DB race."""
        ...
