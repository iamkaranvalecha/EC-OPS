from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import Order, OrderItem, OrderStatus
from src.orders.schemas import OrderCreate, OrderItemCreate
from src.orders.service import cancel_order, create_order, get_order, list_orders


def _make_order(
    status: OrderStatus = OrderStatus.PENDING,
    customer_name: str = "Alice",
) -> Order:
    order = Order(customer_name=customer_name)
    order.id = uuid.uuid4()
    order.status = status
    item = OrderItem(product_name="Widget", quantity=2, price=Decimal("5.00"))
    item.id = uuid.uuid4()
    item.order_id = order.id
    order.items = [item]
    return order


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ── create_order ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order():
    session = _mock_session()

    data = OrderCreate(
        customer_name="Bob",
        items=[OrderItemCreate(product_name="Gizmo", quantity=1, price=Decimal("9.99"))],
    )

    created = await create_order(data, session)

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()
    assert created.customer_name == "Bob"
    assert len(created.items) == 1
    assert created.items[0].product_name == "Gizmo"


# ── get_order ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_found():
    session = _mock_session()
    order = _make_order()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)

    fetched = await get_order(order.id, session)

    assert fetched is order


@pytest.mark.asyncio
async def test_get_order_not_found():
    session = _mock_session()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(OrderNotFound):
        await get_order(uuid.uuid4(), session)


# ── list_orders ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_orders_no_filter():
    session = _mock_session()
    orders = [_make_order(), _make_order(status=OrderStatus.PROCESSING)]
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = orders
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    fetched = await list_orders(session)

    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_list_orders_with_status_filter():
    session = _mock_session()
    pending_order = _make_order(status=OrderStatus.PENDING)
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [pending_order]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    fetched = await list_orders(session, status=OrderStatus.PENDING)

    assert len(fetched) == 1
    assert fetched[0].status == OrderStatus.PENDING


# ── cancel_order ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_order_pending():
    session = _mock_session()
    order = _make_order(status=OrderStatus.PENDING)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)

    await cancel_order(order.id, session)

    session.delete.assert_awaited_once_with(order)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_order_not_pending():
    session = _mock_session()
    order = _make_order(status=OrderStatus.PROCESSING)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(OrderNotCancellable):
        await cancel_order(order.id, session)


@pytest.mark.asyncio
async def test_cancel_order_not_found():
    session = _mock_session()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(OrderNotFound):
        await cancel_order(uuid.uuid4(), session)


# ── integration (live DB) ─────────────────────────────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires live DB — set DATABASE_URL to run",
)
@pytest.mark.asyncio
async def test_create_get_list_cancel_integration():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core.database import Base

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            data = OrderCreate(
                customer_name="Integration Tester",
                items=[
                    OrderItemCreate(product_name="Alpha", quantity=3, price=Decimal("10.00")),
                    OrderItemCreate(product_name="Beta", quantity=1, price=Decimal("25.50")),
                ],
            )
            order = await create_order(data, session)
            assert order.id is not None
            assert len(order.items) == 2

        async with session_factory() as session:
            fetched = await get_order(order.id, session)
            assert fetched.customer_name == "Integration Tester"

        async with session_factory() as session:
            all_orders = await list_orders(session)
            assert any(o.id == order.id for o in all_orders)

            pending_orders = await list_orders(session, status=OrderStatus.PENDING)
            assert any(o.id == order.id for o in pending_orders)

        async with session_factory() as session:
            processing_order = await get_order(order.id, session)
            processing_order.status = OrderStatus.PROCESSING
            await session.commit()

        async with session_factory() as session:
            with pytest.raises(OrderNotCancellable):
                await cancel_order(order.id, session)

    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
