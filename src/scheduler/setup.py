from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.scheduler.jobs import promote_pending_orders


def create_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    The scheduler is returned un-started; the FastAPI lifespan is responsible
    for calling ``scheduler.start()`` and ``scheduler.shutdown()``.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        promote_pending_orders,
        trigger=IntervalTrigger(minutes=5),
        args=[session_factory],
        id="promote_pending_orders",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
