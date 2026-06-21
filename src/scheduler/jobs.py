from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.orders.models import Order, OrderStatus

logger = logging.getLogger(__name__)


async def promote_pending_orders(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Set all PENDING orders to PROCESSING.

    This function is called directly by tests (no APScheduler dependency) and
    is also registered as the APScheduler job payload via ``args=[session_factory]``.
    """
    logger.info("scheduler: promote_pending_orders — starting")
    async with session_factory() as session:
        result = await session.execute(
            update(Order)
            .where(Order.status == OrderStatus.PENDING)
            .values(status=OrderStatus.PROCESSING, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
    count = getattr(result, "rowcount", 0) or 0
    if count:
        logger.info("scheduler: promoted %d order(s) PENDING → PROCESSING", count)
    else:
        logger.info("scheduler: no PENDING orders to promote")
