"""SQLAlchemy implementation of UserRepository."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.domain.entities import User, UserRole
from app.modules.iam.domain.errors import DuplicateEmailError
from app.modules.iam.domain.repository import UserRepository
from app.modules.iam.infrastructure.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, normalized_email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(
                func.lower(UserModel.email) == normalized_email.lower()
            )
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return User(
            id=orm.id,
            email=orm.email,
            password_hash=orm.password_hash,
            role=cast(UserRole, orm.role),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                role=user.role,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateEmailError("Email already registered") from exc
