from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import Order, OrderItem, OrderStatus
from src.orders.schemas import OrderCreate

logger = logging.getLogger(__name__)


async def create_order(
    data: OrderCreate,
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
) -> Order:
    order = Order(customer_name=data.customer_name, user_id=user_id)
    for item_data in data.items:
        item = OrderItem(
            product_name=item_data.product_name,
            quantity=item_data.quantity,
            price=item_data.price,
        )
        order.items.append(item)
    session.add(order)
    await session.commit()
    await session.refresh(order)
    logger.info(
        "order created: id=%s user=%s customer=%r items=%d",
        order.id,
        user_id,
        order.customer_name,
        len(order.items),
    )
    return order


async def get_order(
    order_id: uuid.UUID,
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
    
) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        logger.warning("order not found: id=%s user=%s", order_id, user_id)
        raise OrderNotFound(order_id)
    return order


async def list_orders(
    session: AsyncSession,
    status: OrderStatus | None = None,
    user_id: uuid.UUID | None = None,
) -> list[Order]:
    stmt = select(Order)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    logger.info("orders listed: count=%d filter=%s user=%s", len(orders), status.value if status else "all", user_id)
    return orders


async def find_orders_by_product(
    product_query: str,
    session: AsyncSession,
    status: OrderStatus | None = None,
    user_id: uuid.UUID | None = None,
) -> list[Order]:
    """Return orders that contain at least one item whose product_name matches product_query.

    Case-insensitive partial match (ILIKE). Useful when a user refers to an order by
    product name rather than ID (e.g. 'my refrigerator order').
    """
    stmt = (
        select(Order)
        .join(Order.items)
        .where(OrderItem.product_name.ilike(f"%{product_query}%"))
        .options(selectinload(Order.items))
        .distinct()
    )
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    logger.info(
        "orders found by product: query=%r count=%d filter=%s user=%s",
        product_query, len(orders), status.value if status else "all", user_id,
    )
    return orders


async def cancel_order(
    order_id: uuid.UUID,
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
) -> None:
    order = await get_order(order_id, session, user_id=user_id)
    if order.status != OrderStatus.PENDING:
        logger.warning(
            "cancel rejected: order %s is %s (only PENDING orders can be cancelled)",
            order_id,
            order.status.value,
        )
        raise OrderNotCancellable(order_id, order.status.value)
    order.status = OrderStatus.CANCELLED
    order.updated_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("order cancelled: id=%s user=%s", order_id, user_id)
