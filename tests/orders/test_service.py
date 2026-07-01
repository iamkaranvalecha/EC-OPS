from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orders.exceptions import OrderNotCancellable, OrderNotFound, OrderStatusTransitionError
from src.orders.models import Order, OrderItem, OrderStatus
from src.orders.schemas import OrderCreate, OrderItemCreate
from src.orders.service import cancel_order, create_order, find_orders_by_product, get_order, list_orders, update_order_status


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

    assert order.status == OrderStatus.CANCELLED
    assert order.updated_at is not None
    session.delete.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_order_already_cancelled_raises():
    session = _mock_session()
    order = _make_order(status=OrderStatus.CANCELLED)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(OrderNotCancellable):
        await cancel_order(order.id, session)


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


# ── update_order_status ───────────────────────────────────────────────────────


def _session_returning(order: Order) -> AsyncMock:
    session = _mock_session()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.mark.asyncio
async def test_update_order_status_pending_to_processing():
    order = _make_order(status=OrderStatus.PENDING)
    session = _session_returning(order)

    updated = await update_order_status(order.id, OrderStatus.PROCESSING, session)

    assert updated.status == OrderStatus.PROCESSING
    assert updated.updated_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_order_status_processing_to_shipped():
    order = _make_order(status=OrderStatus.PROCESSING)
    session = _session_returning(order)

    updated = await update_order_status(order.id, OrderStatus.SHIPPED, session)

    assert updated.status == OrderStatus.SHIPPED


@pytest.mark.asyncio
async def test_update_order_status_shipped_to_delivered():
    order = _make_order(status=OrderStatus.SHIPPED)
    session = _session_returning(order)

    updated = await update_order_status(order.id, OrderStatus.DELIVERED, session)

    assert updated.status == OrderStatus.DELIVERED


@pytest.mark.asyncio
async def test_update_order_status_invalid_transition_raises():
    order = _make_order(status=OrderStatus.PENDING)
    session = _session_returning(order)

    with pytest.raises(OrderStatusTransitionError):
        await update_order_status(order.id, OrderStatus.DELIVERED, session)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_order_status_terminal_delivered_raises():
    order = _make_order(status=OrderStatus.DELIVERED)
    session = _session_returning(order)

    with pytest.raises(OrderStatusTransitionError):
        await update_order_status(order.id, OrderStatus.SHIPPED, session)


@pytest.mark.asyncio
async def test_update_order_status_terminal_cancelled_raises():
    order = _make_order(status=OrderStatus.CANCELLED)
    session = _session_returning(order)

    with pytest.raises(OrderStatusTransitionError):
        await update_order_status(order.id, OrderStatus.PROCESSING, session)


@pytest.mark.asyncio
async def test_update_order_status_not_found_raises():
    session = _mock_session()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(OrderNotFound):
        await update_order_status(uuid.uuid4(), OrderStatus.PROCESSING, session)


# ── find_orders_by_product ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_orders_by_product_match():
    session = _mock_session()
    order = _make_order()
    order.items[0].product_name = "Refrigerator"

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [order]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    found = await find_orders_by_product("Refrig", session)
    assert len(found) == 1
    assert found[0].items[0].product_name == "Refrigerator"


@pytest.mark.asyncio
async def test_find_orders_by_product_no_match():
    session = _mock_session()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    found = await find_orders_by_product("Toaster", session)
    assert found == []


# ── integration (live DB) ─────────────────────────────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requires live test DB — set TEST_DATABASE_URL to run",
)
@pytest.mark.asyncio
async def test_create_get_list_cancel_integration():
    from dotenv import dotenv_values
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    _env = dotenv_values(".env")
    # Always use the TEST database — never touch the application DB
    url = (
        os.environ.get("TEST_DATABASE_URL")
        or _env.get("TEST_DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test"
    )
    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

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

        # Cancel the PENDING order — should soft-delete (status → CANCELLED, record kept)
        async with session_factory() as session:
            await cancel_order(order.id, session)

        async with session_factory() as session:
            cancelled = await get_order(order.id, session)
            assert cancelled.status == OrderStatus.CANCELLED
            assert cancelled.updated_at is not None

        # Attempting to cancel an already-CANCELLED order raises OrderNotCancellable
        async with session_factory() as session:
            with pytest.raises(OrderNotCancellable):
                await cancel_order(order.id, session)

        # CANCELLED appears in the unfiltered list
        async with session_factory() as session:
            all_orders = await list_orders(session)
            assert any(o.id == order.id and o.status == OrderStatus.CANCELLED for o in all_orders)

        # CANCELLED appears when filtering by status=CANCELLED
        async with session_factory() as session:
            cancelled_orders = await list_orders(session, status=OrderStatus.CANCELLED)
            assert any(o.id == order.id for o in cancelled_orders)

    finally:
        # Do NOT drop_all — tables are shared with the test suite.
        # Row cleanup is handled by the autouse db_setup fixture (TRUNCATE orders CASCADE).
        await engine.dispose()
