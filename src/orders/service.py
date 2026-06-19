from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import Order, OrderItem, OrderStatus
from src.orders.schemas import OrderCreate


async def create_order(data: OrderCreate, session: AsyncSession) -> Order:
    order = Order(customer_name=data.customer_name)
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
    return order


async def get_order(order_id: uuid.UUID, session: AsyncSession) -> Order:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise OrderNotFound(order_id)
    return order


async def list_orders(
    session: AsyncSession,
    status: OrderStatus | None = None,
) -> list[Order]:
    stmt = select(Order)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def cancel_order(order_id: uuid.UUID, session: AsyncSession) -> None:
    order = await get_order(order_id, session)
    if order.status != OrderStatus.PENDING:
        raise OrderNotCancellable(order_id, order.status.value)
    await session.delete(order)
    await session.commit()
