from collections.abc import AsyncGenerator
from importlib import import_module
from urllib.parse import urlparse, urlunparse

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config import get_settings
from app.shared.db.base import Base

_model_paths = [
    "app.shared.events.models",
    "app.shared.messaging.models",
    "app.modules.orders.infrastructure.models",
    "app.modules.inventory.infrastructure.models",
    "app.modules.payments.infrastructure.models",
    "app.modules.notifications.infrastructure.models",
]

for _path in _model_paths:
    try:
        import_module(_path)
    except ImportError:
        pass

settings = get_settings()
_parsed = urlparse(str(settings.database_url))
_db = f"{_parsed.path[1:]}_test"
TEST_DATABASE_URL = urlunparse(_parsed._replace(path=f"/{_db}"))


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
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
