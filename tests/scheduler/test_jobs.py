from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import dotenv_values

from src.orders.models import OrderStatus
from src.scheduler.jobs import promote_pending_orders

# ---------------------------------------------------------------------------
# Helpers for unit tests
# ---------------------------------------------------------------------------

_env = dotenv_values(".env")
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    """Return (factory, session) where factory() returns the session context manager."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    # Make the factory usable as `async with session_factory() as session:`
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory, session


# ---------------------------------------------------------------------------
# Unit tests (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_pending_orders_executes_update():
    """Happy path: promote_pending_orders calls execute + commit on the session."""
    factory, session = _mock_session_factory()

    await promote_pending_orders(factory)

    factory.assert_called_once()
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_promote_pending_orders_update_contains_processing_status():
    """The UPDATE statement targets PENDING and sets PROCESSING."""
    factory, session = _mock_session_factory()

    await promote_pending_orders(factory)

    call_args = session.execute.call_args
    assert call_args is not None, "session.execute was not called"

    # Inspect the compiled SQL to confirm the intent of the statement
    stmt = call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "PROCESSING" in compiled
    assert "PENDING" in compiled


@pytest.mark.asyncio
async def test_promote_pending_orders_commit_called_after_execute():
    """Commit is issued after the UPDATE (ordering verified via call_count)."""
    factory, session = _mock_session_factory()
    call_order: list[str] = []

    async def record_execute(*args, **kwargs):  # noqa: ARG001
        call_order.append("execute")

    async def record_commit():
        call_order.append("commit")

    session.execute = AsyncMock(side_effect=record_execute)
    session.commit = AsyncMock(side_effect=record_commit)

    await promote_pending_orders(factory)

    assert call_order == ["execute", "commit"]


@pytest.mark.asyncio
async def test_promote_pending_orders_session_opened_via_factory():
    """The factory context-manager is entered (i.e. a session is opened)."""
    factory, session = _mock_session_factory()

    await promote_pending_orders(factory)

    cm = factory.return_value
    cm.__aenter__.assert_awaited_once()
    cm.__aexit__.assert_awaited_once()


# ---------------------------------------------------------------------------
# Integration test (real DB, gated on TEST_DATABASE_URL)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _TEST_DB_URL,
    reason="requires live DB — set TEST_DATABASE_URL in .env or environment",
)
@pytest.mark.asyncio
async def test_promote_pending_orders_integration():
    """Integration: PENDING orders become PROCESSING; other statuses are unchanged."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.database import Base
    from src.orders.models import Order

    engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Ensure tables exist (idempotent)
    non_vector = [t for t in Base.metadata.tables.values() if "embedding" not in t.name]
    for table in non_vector:
        async with engine.begin() as conn:
            await conn.run_sync(table.create, checkfirst=True)

    # Seed one order per status
    pending_id = uuid.uuid4()
    processing_id = uuid.uuid4()
    shipped_id = uuid.uuid4()
    delivered_id = uuid.uuid4()

    async with session_factory() as session:
        for oid, status in [
            (pending_id, OrderStatus.PENDING),
            (processing_id, OrderStatus.PROCESSING),
            (shipped_id, OrderStatus.SHIPPED),
            (delivered_id, OrderStatus.DELIVERED),
        ]:
            order = Order(customer_name="Scheduler Test")
            order.id = oid
            order.status = status
            session.add(order)
        await session.commit()

    try:
        # Run the job
        await promote_pending_orders(session_factory)

        # Assert outcomes
        async with session_factory() as session:
            result = await session.execute(select(Order))
            orders = {o.id: o for o in result.scalars().all()}

        assert orders[pending_id].status == OrderStatus.PROCESSING, (
            "PENDING order must be promoted to PROCESSING"
        )
        assert orders[processing_id].status == OrderStatus.PROCESSING, (
            "PROCESSING order must remain PROCESSING"
        )
        assert orders[shipped_id].status == OrderStatus.SHIPPED, (
            "SHIPPED order must remain SHIPPED"
        )
        assert orders[delivered_id].status == OrderStatus.DELIVERED, (
            "DELIVERED order must remain DELIVERED"
        )

        # The promoted order must have updated_at set
        assert orders[pending_id].updated_at is not None, (
            "updated_at must be set after promotion"
        )

    finally:
        # Clean up seeded rows using SQLAlchemy core (asyncpg does not support
        # the `::cast` syntax inside parameterised text queries).
        from sqlalchemy import delete as sa_delete

        seeded_ids = [pending_id, processing_id, shipped_id, delivered_id]
        async with session_factory() as session:
            await session.execute(sa_delete(Order).where(Order.id.in_(seeded_ids)))
            await session.commit()
        await engine.dispose()
