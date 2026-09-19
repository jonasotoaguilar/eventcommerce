"""RegisterUser use case: always creates a shopper."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.iam.application.passwords import hash_password
from app.modules.iam.domain.entities import User, normalize_email
from app.modules.iam.domain.errors import DuplicateEmailError
from app.modules.iam.domain.repository import UserRepository

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


async def register_user(repository: UserRepository, email: str, password: str) -> User:
    """Register a new shopper; DuplicateEmailError when the email exists."""
    normalized = normalize_email(email)
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters"
        )
    if await repository.get_by_email(normalized) is not None:
        raise DuplicateEmailError("Email already registered")
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        email=normalized,
        password_hash=hash_password(password),
        role="shopper",
        created_at=now,
        updated_at=now,
    )
    await repository.add(user)
    return user
