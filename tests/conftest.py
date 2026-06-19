from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.database import Base
from src.core.dependencies import get_session
from src.main import app

_env = dotenv_values(".env")
# No fallback — used to decide if a real DB is configured
_explicit_db_url: str | None = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")
# With fallback — engine always gets a URL string
TEST_DATABASE_URL: str = _explicit_db_url or "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test"

# NullPool: no connection caching; avoids "Future attached to different loop" across tests
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

_TABLES_CREATED = False


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    """Create tables once per process, truncate data after every test."""
    if not _explicit_db_url:
        yield
        return
    global _TABLES_CREATED
    if not _TABLES_CREATED:
        non_vector = [t for t in Base.metadata.tables.values() if "embedding" not in t.name]
        for table in non_vector:
            async with test_engine.begin() as conn:
                await conn.run_sync(table.create, checkfirst=True)
        _TABLES_CREATED = True
    yield
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE orders CASCADE"))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Expose the shared session factory for tests that need it directly (e.g. scheduler tests)."""
    return _session_factory


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
