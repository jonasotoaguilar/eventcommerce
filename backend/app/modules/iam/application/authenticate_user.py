"""AuthenticateUser use case: generic failure for every cause."""

from app.modules.iam.application.passwords import DUMMY_HASH, verify_password
from app.modules.iam.domain.entities import User, normalize_email
from app.modules.iam.domain.errors import InvalidCredentialsError
from app.modules.iam.domain.repository import UserRepository


async def authenticate_user(
    repository: UserRepository, email: str, password: str
) -> User:
    """Return the user on success; InvalidCredentialsError otherwise."""
    user = await repository.get_by_email(normalize_email(email))
    candidate_hash = user.password_hash if user is not None else DUMMY_HASH
    if not verify_password(password, candidate_hash):
        raise InvalidCredentialsError("Invalid email or password")
    if user is None:
        raise InvalidCredentialsError("Invalid email or password")
    return user
