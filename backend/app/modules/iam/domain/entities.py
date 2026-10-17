"""IAM domain entities."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

UserRole = Literal["shopper", "operator"]

ALLOWED_ROLES: tuple[str, ...] = ("shopper", "operator")


def normalize_email(email: str) -> str:
    """Trim surrounding whitespace and Unicode-casefold one email address."""
    return email.strip().casefold()


@dataclass
class RefreshToken:
    id: UUID
    user_id: UUID
    family_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("created_at", "expires_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        for name in ("consumed_at", "revoked_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")


@dataclass
class User:
    id: UUID
    email: str
    password_hash: str
    role: UserRole = "shopper"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"Unknown role: {self.role}")
        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
