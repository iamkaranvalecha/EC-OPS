from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.database import Base
from src.core.dependencies import get_session
from src.main import app
from src.orders.models import Order, OrderStatus

# Read from .env without polluting os.environ (which would enable DB-gated
# skipped tests in other modules that check os.environ.get("DATABASE_URL")).
_env = dotenv_values(".env")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _env.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test",
)

# NullPool: no connection caching — each use creates a fresh connection in the
# current event loop, avoiding "Future attached to different loop" across tests.
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

_TABLES_CREATED = False


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    """Ensure tables exist (idempotent), then truncate after each test."""
    global _TABLES_CREATED
    if not _TABLES_CREATED:
        non_vector = [t for t in Base.metadata.tables.values() if "embedding" not in t.name]
        for table in non_vector:
            async with test_engine.begin() as conn:
                await conn.run_sync(table.create, checkfirst=True)
        _TABLES_CREATED = True

    yield

    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE order_items, orders CASCADE"))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_get_list_cancel_flow(api_client: AsyncClient):
    create_response = await api_client.post(
        "/orders",
        json={
            "customer_name": "Integration Tester",
            "items": [
                {"product_name": "Alpha", "quantity": 3, "price": "10.00"},
                {"product_name": "Beta", "quantity": 1, "price": "25.50"},
            ],
        },
    )
    assert create_response.status_code == 201
    order = create_response.json()
    order_id = order["id"]
    assert order["customer_name"] == "Integration Tester"
    assert order["status"] == "PENDING"
    assert len(order["items"]) == 2

    get_response = await api_client.get(f"/orders/{order_id}")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == order_id
    assert fetched["customer_name"] == "Integration Tester"

    list_response = await api_client.get("/orders")
    assert list_response.status_code == 200
    all_orders = list_response.json()
    assert any(o["id"] == order_id for o in all_orders)

    filtered_response = await api_client.get("/orders?status=PENDING")
    assert filtered_response.status_code == 200
    pending_orders = filtered_response.json()
    assert any(o["id"] == order_id for o in pending_orders)

    cancel_response = await api_client.delete(f"/orders/{order_id}")
    assert cancel_response.status_code == 204

    get_after_cancel = await api_client.get(f"/orders/{order_id}")
    assert get_after_cancel.status_code == 404


@pytest.mark.asyncio
async def test_cancel_non_pending_order_returns_409(
    api_client: AsyncClient, db_session: AsyncSession
):
    create_response = await api_client.post(
        "/orders",
        json={
            "customer_name": "Status Tester",
            "items": [{"product_name": "Gamma", "quantity": 1, "price": "5.00"}],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    result = await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id))
    )
    db_order = result.scalar_one()
    db_order.status = OrderStatus.PROCESSING
    await db_session.commit()

    cancel_response = await api_client.delete(f"/orders/{order_id}")
    assert cancel_response.status_code == 409


@pytest.mark.asyncio
async def test_get_nonexistent_order_returns_404(api_client: AsyncClient):
    fake_id = uuid.uuid4()
    response = await api_client.get(f"/orders/{fake_id}")
    assert response.status_code == 404
