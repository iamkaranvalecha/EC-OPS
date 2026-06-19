import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def ingest_order_embeddings(order_id: uuid.UUID, session: AsyncSession) -> None:
    logger.info("embedding not wired")


async def retrieve_similar_orders(
    query: str, session: AsyncSession, top_k: int = 5
) -> list:
    return []
