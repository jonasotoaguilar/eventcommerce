"""Pytest fixtures for backend tests."""

import app.modules.orders.infrastructure.models  # noqa: F401
import app.modules.inventory.infrastructure.models  # noqa: F401
import app.modules.payments.infrastructure.models  # noqa: F401
import app.modules.notifications.infrastructure.models  # noqa: F401
import app.shared.events.models  # noqa: F401
import app.shared.messaging.models  # noqa: F401
import pytest_asyncio
from app.shared.config import get_settings
from app.shared.db.base import Base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

settings = get_settings()
TEST_DATABASE_URL = settings.test_database_url


@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
