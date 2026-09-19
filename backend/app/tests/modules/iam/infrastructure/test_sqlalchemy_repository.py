"""Repository contract tests for the SQLAlchemy IAM user repository.

Runs against the disposable PostgreSQL used by the ``engine`` /
``db_session`` fixtures in ``backend/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.iam.domain.entities import User, normalize_email
from app.modules.iam.domain.errors import DuplicateEmailError
from app.modules.iam.infrastructure import models as _iam_models  # noqa: F401
from app.modules.iam.infrastructure.sqlalchemy_repository import (
    SqlAlchemyUserRepository,
)

assert _iam_models is not None


def _user(email: str) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email=normalize_email(email),
        password_hash="hash-" + uuid4().hex,
        role="shopper",
        created_at=now,
        updated_at=now,
    )


class TestSqlAlchemyUserRepository:
    @pytest.mark.asyncio
    async def test_add_and_get_by_email_round_trip(self, db_session) -> None:
        repo = SqlAlchemyUserRepository(db_session)
        user = _user("Shopper@Example.com")

        await repo.add(user)
        found = await repo.get_by_email(user.email)

        assert found is not None
        assert found.id == user.id
        assert found.email == user.email
        assert found.password_hash == user.password_hash
        assert found.role == user.role

    @pytest.mark.asyncio
    async def test_get_by_email_is_case_insensitive(self, db_session) -> None:
        repo = SqlAlchemyUserRepository(db_session)
        await repo.add(_user("Case@Test.com"))

        assert await repo.get_by_email("case@test.com") is not None
        assert await repo.get_by_email("CASE@TEST.COM") is not None
        assert await repo.get_by_email("CaSe@tEsT.cOm") is not None

    @pytest.mark.asyncio
    async def test_get_by_email_returns_none_when_unknown(self, db_session) -> None:
        repo = SqlAlchemyUserRepository(db_session)

        assert await repo.get_by_email("nobody@example.com") is None

    @pytest.mark.asyncio
    async def test_add_duplicate_email_raises_after_precheck_hit(
        self, db_session
    ) -> None:
        repo = SqlAlchemyUserRepository(db_session)
        await repo.add(_user("dupe@example.com"))
        await db_session.commit()

        # Precheck a second registration would run sees the clash.
        assert await repo.get_by_email("dupe@example.com") is not None

        # The race safety net still converts the DB violation.
        with pytest.raises(DuplicateEmailError):
            await repo.add(_user("dupe@example.com"))

    @pytest.mark.asyncio
    async def test_add_duplicate_email_case_variant_raises(self, db_session) -> None:
        repo = SqlAlchemyUserRepository(db_session)
        await repo.add(_user("Shopper@Example.com"))
        await db_session.commit()

        with pytest.raises(DuplicateEmailError):
            await repo.add(_user("shopper@example.com"))

    @pytest.mark.asyncio
    async def test_concurrent_sessions_duplicate_race_raises(
        self, engine, db_session
    ) -> None:
        first = SqlAlchemyUserRepository(db_session)
        await first.add(_user("race@example.com"))
        await db_session.commit()

        maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with maker() as second_session:
            second = SqlAlchemyUserRepository(second_session)
            with pytest.raises(DuplicateEmailError):
                await second.add(_user("RACE@example.com"))
            await second_session.rollback()

        # First session is unaffected by the loser's rollback.
        assert await first.get_by_email("race@example.com") is not None

    @pytest.mark.asyncio
    async def test_session_usable_after_duplicate_race(self, db_session) -> None:
        repo = SqlAlchemyUserRepository(db_session)
        await repo.add(_user("kept@example.com"))
        await db_session.commit()

        with pytest.raises(DuplicateEmailError):
            await repo.add(_user("KEPT@example.com"))

        # Generic behavior is unchanged: the session still persists new rows.
        await repo.add(_user("fresh@example.com"))
        assert await repo.get_by_email("kept@example.com") is not None
        assert await repo.get_by_email("fresh@example.com") is not None
