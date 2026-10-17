"""Refresh-token rotation route tests (W3/S2): hashed storage, rotation, reuse.

Runs over real HTTP against the disposable PostgreSQL used by the
``engine`` fixture in ``backend/conftest.py``, following the conventions
in ``test_routes.py`` (``test_settings``/``client`` fixtures, monkeypatched
``get_settings``).
"""

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api import dependencies as iam_dependencies
from app.modules.iam.application import refresh_tokens as iam_refresh
from app.modules.iam.application import tokens as iam_tokens
from app.modules.iam.application.refresh_tokens import (
    issue_refresh_token,
    rotate_refresh_token,
)
from app.modules.iam.application.register_user import register_user
from app.modules.iam.domain.entities import RefreshToken
from app.modules.iam.domain.errors import InvalidTokenError
from app.modules.iam.infrastructure import models as _iam_models  # noqa: F401
from app.modules.iam.infrastructure.models import RefreshTokenModel
from app.modules.iam.infrastructure.sqlalchemy_refresh_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from app.modules.iam.infrastructure.sqlalchemy_repository import (
    SqlAlchemyUserRepository,
)
from app.shared.config.settings import Settings
from app.shared.db.session import get_db_session

assert _iam_models is not None


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret=secrets.token_urlsafe(32),
        jwt_issuer="iam-test-issuer",
        jwt_audience="iam-test-audience",
    )


@pytest.fixture
def client(engine, monkeypatch, test_settings) -> TestClient:
    monkeypatch.setattr(iam_tokens, "get_settings", lambda: test_settings)
    monkeypatch.setattr(iam_refresh, "get_settings", lambda: test_settings)
    monkeypatch.setattr(iam_dependencies, "get_settings", lambda: test_settings)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "valid-pass-1"):
    return client.post(
        "/api/v1/iam/register", json={"email": email, "password": password}
    )


def _login(client: TestClient, email: str, password: str = "valid-pass-1"):
    return client.post("/api/v1/iam/login", json={"email": email, "password": password})


def _refresh(client: TestClient, refresh_token: str):
    return client.post("/api/v1/iam/refresh", json={"refresh_token": refresh_token})


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TestLoginIssuesRefreshToken:
    def test_login_returns_access_and_refresh_pair(self, client: TestClient) -> None:
        _register(client, "login@example.com")

        response = _login(client, "login@example.com")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "refresh_token", "token_type"}
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["refresh_token"] != body["access_token"]

    def test_refresh_token_is_opaque_not_jwt(self, client: TestClient) -> None:
        _register(client, "opaque@example.com")
        refresh_token = _login(client, "opaque@example.com").json()["refresh_token"]

        assert "." not in refresh_token

        me = client.get(
            "/api/v1/iam/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert me.status_code == 401

    def test_consecutive_logins_issue_distinct_refresh_tokens(
        self, client: TestClient
    ) -> None:
        _register(client, "multi@example.com")

        first = _login(client, "multi@example.com").json()
        second = _login(client, "multi@example.com").json()

        assert first["refresh_token"] != second["refresh_token"]

    def test_register_still_returns_no_token(self, client: TestClient) -> None:
        response = _register(client, "fresh@example.com")

        assert response.status_code == 201
        assert set(response.json()) == {"user_id", "email", "role"}


class TestRefreshRotation:
    def test_refresh_returns_new_pair_and_new_access_works(
        self, client: TestClient
    ) -> None:
        _register(client, "rotate@example.com")
        first = _login(client, "rotate@example.com").json()

        response = _refresh(client, first["refresh_token"])

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "refresh_token", "token_type"}
        assert body["token_type"] == "bearer"
        assert body["refresh_token"] != first["refresh_token"]

        me = client.get(
            "/api/v1/iam/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "rotate@example.com"

    def test_exchanged_token_is_rejected_on_replay(self, client: TestClient) -> None:
        _register(client, "replay@example.com")
        first = _login(client, "replay@example.com").json()
        assert _refresh(client, first["refresh_token"]).status_code == 200

        replay = _refresh(client, first["refresh_token"])

        assert replay.status_code == 401

    def test_replay_revokes_family_so_newest_token_stops_working(
        self, client: TestClient
    ) -> None:
        _register(client, "family@example.com")
        first = _login(client, "family@example.com").json()
        rotated = _refresh(client, first["refresh_token"]).json()

        assert _refresh(client, first["refresh_token"]).status_code == 401

        newest = _refresh(client, rotated["refresh_token"])
        assert newest.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_revoked_unknown_share_indistinguishable_401(
        self, client: TestClient, engine
    ) -> None:
        _register(client, "indistinguishable@example.com")
        first = _login(client, "indistinguishable@example.com").json()
        rotated = _refresh(client, first["refresh_token"]).json()
        assert _refresh(client, first["refresh_token"]).status_code == 401

        _register(client, "expired@example.com")
        expiring = _login(client, "expired@example.com").json()["refresh_token"]
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(
                update(RefreshTokenModel)
                .where(RefreshTokenModel.token_hash == _digest(expiring))
                .values(expires_at=datetime.now(timezone.utc))
            )
            await session.commit()

        expired = _refresh(client, expiring)
        revoked_newest = _refresh(client, rotated["refresh_token"])
        replayed = _refresh(client, first["refresh_token"])
        unknown = _refresh(client, secrets.token_urlsafe(32))
        blank = _refresh(client, "")

        for response in (expired, revoked_newest, replayed, unknown, blank):
            assert response.status_code == 401
        details = {
            response.json()["detail"]
            for response in (expired, revoked_newest, replayed, unknown, blank)
        }
        assert len(details) == 1

    def test_refresh_mints_session_for_token_owner_only(
        self, client: TestClient
    ) -> None:
        _register(client, "owner-a@example.com")
        _register(client, "owner-b@example.com")
        token_a = _login(client, "owner-a@example.com").json()["refresh_token"]
        token_b = _login(client, "owner-b@example.com").json()["refresh_token"]

        me_a = client.get(
            "/api/v1/iam/me",
            headers={
                "Authorization": (
                    f"Bearer {_refresh(client, token_a).json()['access_token']}"
                )
            },
        )
        me_b = client.get(
            "/api/v1/iam/me",
            headers={
                "Authorization": (
                    f"Bearer {_refresh(client, token_b).json()['access_token']}"
                )
            },
        )

        assert me_a.json()["email"] == "owner-a@example.com"
        assert me_b.json()["email"] == "owner-b@example.com"


class TestStoredRefreshRows:
    @pytest.mark.asyncio
    async def test_stored_row_holds_hash_never_plaintext(
        self, client: TestClient, engine
    ) -> None:
        _register(client, "stored@example.com")
        refresh_token = _login(client, "stored@example.com").json()["refresh_token"]

        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            rows = (await session.execute(select(RefreshTokenModel))).scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.token_hash == _digest(refresh_token)
        assert row.token_hash != refresh_token
        for value in (str(row.id), str(row.family_id), str(row.user_id)):
            assert value != refresh_token
        assert row.consumed_at is None
        assert row.revoked_at is None
        assert row.expires_at > row.created_at

    @pytest.mark.asyncio
    async def test_rotation_links_new_row_to_same_family(
        self, client: TestClient, engine
    ) -> None:
        _register(client, "lineage@example.com")
        first = _login(client, "lineage@example.com").json()["refresh_token"]
        second = _refresh(client, first).json()["refresh_token"]

        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            rows = (await session.execute(select(RefreshTokenModel))).scalars().all()

        assert len(rows) == 2
        by_hash = {row.token_hash: row for row in rows}
        old = by_hash[_digest(first)]
        new = by_hash[_digest(second)]
        assert old.family_id == new.family_id
        assert old.consumed_at is not None
        assert new.consumed_at is None
        assert old.revoked_at is None
        assert new.revoked_at is None


class TestConcurrentRefresh:
    @pytest.mark.asyncio
    async def test_double_spend_lets_exactly_one_winner_through(
        self, engine, test_settings: Settings, monkeypatch
    ) -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as seed:
            users = SqlAlchemyUserRepository(seed)
            tokens = SqlAlchemyRefreshTokenRepository(seed)
            user = await register_user(users, "racer@example.com", "valid-pass-1")
            raw = await issue_refresh_token(tokens, user.id, settings=test_settings)
            await seed.commit()

        # Force the overlap scheduling luck would otherwise decide: both
        # attempts must finish their validation read before either consumes,
        # so the test exercises a true double-spend rather than two
        # sequential rotations.
        gate = asyncio.Event()
        arrived = 0
        original_consume = SqlAlchemyRefreshTokenRepository.consume

        async def gated_consume(self, token_id, at):
            nonlocal arrived
            arrived += 1
            if arrived == 2:
                gate.set()
            await asyncio.wait_for(gate.wait(), timeout=10)
            return await original_consume(self, token_id, at)

        monkeypatch.setattr(SqlAlchemyRefreshTokenRepository, "consume", gated_consume)

        async def attempt() -> str | None:
            async with factory() as session:
                users = SqlAlchemyUserRepository(session)
                tokens = SqlAlchemyRefreshTokenRepository(session)
                try:
                    _, successor = await rotate_refresh_token(users, tokens, raw)
                except InvalidTokenError:
                    await session.commit()
                    return None
                await session.commit()
                return successor

        first, second = await asyncio.gather(attempt(), attempt())

        winners = [value for value in (first, second) if value is not None]
        assert len(winners) == 1

        async with factory() as session:
            users = SqlAlchemyUserRepository(session)
            tokens = SqlAlchemyRefreshTokenRepository(session)
            with pytest.raises(InvalidTokenError):
                await rotate_refresh_token(users, tokens, winners[0])
            await session.commit()
            rows = (await session.execute(select(RefreshTokenModel))).scalars().all()

        assert len(rows) == 2
        assert {row.family_id for row in rows} == {rows[0].family_id}
        assert all(row.revoked_at is not None for row in rows)

    @pytest.mark.asyncio
    async def test_revocation_landing_before_consume_mints_no_successor(
        self, engine, test_settings: Settings, monkeypatch
    ) -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as seed:
            users = SqlAlchemyUserRepository(seed)
            tokens = SqlAlchemyRefreshTokenRepository(seed)
            user = await register_user(
                users, "revoked-race@example.com", "valid-pass-1"
            )
            raw = await issue_refresh_token(tokens, user.id, settings=test_settings)
            stored = await tokens.get_by_hash(_digest(raw))
            assert stored is not None
            family_id = stored.family_id
            await seed.commit()

        # A concurrent replay revokes the family between this request's
        # validation read and its consume, so the read it validated against
        # is stale by the time the token is spent.
        original_get = SqlAlchemyRefreshTokenRepository.get_by_hash
        revoked = False

        async def revoke_after_read(self, token_hash):
            nonlocal revoked
            found = await original_get(self, token_hash)
            if found is not None and not revoked:
                revoked = True
                async with factory() as replay:
                    await SqlAlchemyRefreshTokenRepository(replay).revoke_family(
                        family_id, datetime.now(timezone.utc)
                    )
                    await replay.commit()
            return found

        monkeypatch.setattr(
            SqlAlchemyRefreshTokenRepository, "get_by_hash", revoke_after_read
        )

        async with factory() as session:
            users = SqlAlchemyUserRepository(session)
            tokens = SqlAlchemyRefreshTokenRepository(session)
            with pytest.raises(InvalidTokenError):
                await rotate_refresh_token(users, tokens, raw)
            await session.commit()

        async with factory() as session:
            rows = (await session.execute(select(RefreshTokenModel))).scalars().all()

        assert len(rows) == 1
        assert rows[0].revoked_at is not None

    @pytest.mark.asyncio
    async def test_revocation_racing_successor_insert_revokes_successor(
        self, engine, test_settings: Settings
    ) -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as seed:
            users = SqlAlchemyUserRepository(seed)
            tokens = SqlAlchemyRefreshTokenRepository(seed)
            user = await register_user(users, "insert-race@example.com", "valid-pass-1")
            raw = await issue_refresh_token(tokens, user.id, settings=test_settings)
            stored = await tokens.get_by_hash(_digest(raw))
            assert stored is not None
            family_id, token_id, user_id = stored.family_id, stored.id, stored.user_id
            await seed.commit()

        now = datetime.now(timezone.utc)
        successor_id = uuid4()
        async with factory() as rotating:
            tokens = SqlAlchemyRefreshTokenRepository(rotating)
            assert await tokens.consume(token_id, now) is True
            await tokens.add(
                RefreshToken(
                    id=successor_id,
                    user_id=user_id,
                    family_id=family_id,
                    token_hash=hashlib.sha256(b"successor").hexdigest(),
                    created_at=now,
                    expires_at=now + timedelta(days=14),
                )
            )

            async def revoke() -> None:
                async with factory() as replay:
                    await SqlAlchemyRefreshTokenRepository(replay).revoke_family(
                        family_id, datetime.now(timezone.utc)
                    )
                    await replay.commit()

            task = asyncio.create_task(revoke())
            await asyncio.sleep(0.2)
            assert not task.done()
            await rotating.commit()
            await task

        async with factory() as session:
            row = (
                await session.execute(
                    select(RefreshTokenModel).where(
                        RefreshTokenModel.id == successor_id
                    )
                )
            ).scalar_one()

        assert row.revoked_at is not None
