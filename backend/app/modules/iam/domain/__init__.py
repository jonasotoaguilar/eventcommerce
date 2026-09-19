"""IAM domain package."""

from app.modules.iam.domain.entities import User, normalize_email
from app.modules.iam.domain.errors import DuplicateEmailError, InvalidCredentialsError
from app.modules.iam.domain.repository import UserRepository

__all__ = [
    "DuplicateEmailError",
    "InvalidCredentialsError",
    "User",
    "UserRepository",
    "normalize_email",
]
