from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.orders.models import Order, OrderStatus


async def promote_pending_orders(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Set all PENDING orders to PROCESSING.

    This function is called directly by tests (no APScheduler dependency) and
    is also registered as the APScheduler job payload via ``args=[session_factory]``.
    """
    async with session_factory() as session:
        await session.execute(
            update(Order)
            .where(Order.status == OrderStatus.PENDING)
            .values(status=OrderStatus.PROCESSING, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
