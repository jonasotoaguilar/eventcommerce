from collections.abc import AsyncGenerator
from importlib import import_module
from urllib.parse import urlparse, urlunparse

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config import get_settings
from app.shared.db.base import Base

_model_paths = [
    "app.modules.orders.infrastructure.models",
    "app.modules.inventory.infrastructure.models",
    "app.modules.payments.infrastructure.models",
    "app.modules.notifications.infrastructure.models",
    "app.shared.events.models",
    "app.shared.messaging.models",
]

for _path in _model_paths:
    try:
        import_module(_path)
    except ImportError:
        pass

settings = get_settings()
_test_url = getattr(settings, "test_database_url", None)
if _test_url is None:
    _parsed = urlparse(str(settings.database_url))
    _db = f"{_parsed.path[1:]}_test"
    _test_url = urlunparse(_parsed._replace(path=f"/{_db}"))
TEST_DATABASE_URL = _test_url


@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(str(TEST_DATABASE_URL), future=True)
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
