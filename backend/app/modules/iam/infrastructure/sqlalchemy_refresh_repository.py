"""SQLAlchemy implementation of RefreshTokenRepository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.domain.entities import RefreshToken
from app.modules.iam.domain.repository import RefreshTokenRepository
from app.modules.iam.infrastructure.models import RefreshTokenModel


def _to_entity(orm: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=orm.id,
        user_id=orm.user_id,
        family_id=orm.family_id,
        token_hash=orm.token_hash,
        created_at=orm.created_at,
        expires_at=orm.expires_at,
        consumed_at=orm.consumed_at,
        revoked_at=orm.revoked_at,
    )


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenModel(
                id=token.id,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                created_at=token.created_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=token.revoked_at,
            )
        )
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        orm = result.scalar_one_or_none()
        return _to_entity(orm) if orm is not None else None

    async def consume(self, token_id: UUID, at: datetime) -> bool:
        # Locking the row first serializes this spend against a concurrent
        # family revocation, which locks the same rows; without it the UPDATE
        # below could spend a token the family just revoked.
        await self._session.execute(
            select(RefreshTokenModel.id)
            .where(RefreshTokenModel.id == token_id)
            .with_for_update()
        )
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.id == token_id,
                RefreshTokenModel.consumed_at.is_(None),
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(consumed_at=at)
            .returning(RefreshTokenModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        # Waiting for in-flight rotations here is what keeps the revocation
        # below whole: it runs as its own statement, so it sees the successor
        # a racing rotation inserts instead of missing it behind its snapshot.
        await self._session.execute(
            select(RefreshTokenModel.id)
            .where(RefreshTokenModel.family_id == family_id)
            .with_for_update()
        )
        await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )
        await self._session.flush()
