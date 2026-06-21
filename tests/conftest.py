from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.auth.service import create_access_token, hash_password
from src.core.database import Base
from src.core.dependencies import get_session
from src.main import app

_env = dotenv_values(".env")
# No fallback — used to decide if a real DB is configured
_explicit_db_url: str | None = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")
# With fallback — engine always gets a URL string
TEST_DATABASE_URL: str = (
    _explicit_db_url or "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test"
)

# NullPool: no connection caching; avoids "Future attached to different loop" across tests
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

_TABLES_CREATED = False
_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_TEST_USERNAME = "testuser"
_TEST_PASSWORD = "testpass123"


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    """Create tables once per process; seed a fixture user; truncate order data after each test."""
    if not _explicit_db_url:
        yield
        return
    global _TABLES_CREATED
    if not _TABLES_CREATED:
        non_vector = [t for t in Base.metadata.tables.values() if "embedding" not in t.name]
        for table in non_vector:
            async with test_engine.begin() as conn:
                await conn.run_sync(table.create, checkfirst=True)
        # Ensure all enum values are present (handles the case where the orders table
        # pre-existed before CANCELLED was added — checkfirst=True skips CREATE TABLE
        # entirely, so the old enum is never updated otherwise).
        async with test_engine.begin() as conn:
            await conn.execute(
                text("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
            )
        # Add user_id FK column if the orders table pre-dated this migration.
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE orders"
                    " ADD COLUMN IF NOT EXISTS user_id UUID"
                    " REFERENCES users(id)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id)"
                )
            )
        _TABLES_CREATED = True

    # Seed the persistent fixture user (ON CONFLICT DO NOTHING = idempotent).
    hashed = hash_password(_TEST_PASSWORD)
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, username, hashed_password, is_active, created_at)"
                " VALUES (:id, :username, :hashed_password, true, now())"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"id": _TEST_USER_ID, "username": _TEST_USERNAME, "hashed_password": hashed},
        )

    yield

    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE orders CASCADE"))
        # Remove users created by individual tests; keep the fixture user.
        await conn.execute(
            text("DELETE FROM users WHERE id != :uid"),
            {"uid": _TEST_USER_ID},
        )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Expose the shared session factory for tests that need it directly (e.g. scheduler tests)."""
    return _session_factory


@pytest.fixture
def auth_token() -> str:
    """Valid JWT for the fixture user (no DB round-trip — uses create_access_token directly)."""
    return create_access_token(_TEST_USER_ID, _TEST_USERNAME)


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, auth_token: str
) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with a real JWT header and DB session injected.

    Uses the real auth flow (token → DB lookup) so auth middleware is fully exercised.
    The fixture user is seeded by db_setup.
    """

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def raw_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated client with DB session injected.

    Use for auth tests (register / login) and for verifying that protected
    routes correctly return 401.
    """

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
