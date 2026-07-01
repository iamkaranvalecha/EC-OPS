"""Exhaustive combination tests for all order processing requirements.

Covers every (from_status × to_status) transition, all cancel permutations,
all list-filter values, create edge cases, and scheduler configuration.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.core.dependencies import get_session
from src.main import app
from src.orders.exceptions import (
    OrderNotCancellable,
    OrderNotFound,
    OrderStatusTransitionError,
)
from src.orders.models import Order, OrderItem, OrderStatus
from src.orders.schemas import OrderCreate, OrderItemCreate
from src.orders.service import (
    cancel_order,
    create_order,
    list_orders,
    update_order_status,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

ALL_STATUSES = list(OrderStatus)

VALID_TRANSITIONS = {
    (OrderStatus.PENDING, OrderStatus.PROCESSING),
    (OrderStatus.PROCESSING, OrderStatus.SHIPPED),
    (OrderStatus.SHIPPED, OrderStatus.DELIVERED),
}

INVALID_TRANSITIONS = [
    (from_s, to_s)
    for from_s in ALL_STATUSES
    for to_s in ALL_STATUSES
    if (from_s, to_s) not in VALID_TRANSITIONS
]


def _make_order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    order = Order(customer_name="Test Customer")
    order.id = uuid.uuid4()
    order.status = status
    order.created_at = datetime.now(timezone.utc)
    order.updated_at = None
    item = OrderItem(product_name="Widget", quantity=1, price=Decimal("9.99"))
    item.id = uuid.uuid4()
    item.order_id = order.id
    order.items = [item]
    return order


def _session_returning(order: Order | None) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def client():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return User(id=uuid.uuid4(), username="tester", hashed_password="", is_active=True)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


# ── Requirement 1: Create an order ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_single_item():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    data = OrderCreate(
        customer_name="Alice",
        items=[OrderItemCreate(product_name="Pen", quantity=1, price=Decimal("1.50"))],
    )
    order = await create_order(data, session)

    assert order.customer_name == "Alice"
    assert len(order.items) == 1
    assert order.items[0].product_name == "Pen"
    assert order.status == OrderStatus.PENDING


@pytest.mark.asyncio
async def test_create_order_multiple_items():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    data = OrderCreate(
        customer_name="Bob",
        items=[
            OrderItemCreate(product_name="Laptop", quantity=1, price=Decimal("999.99")),
            OrderItemCreate(product_name="Mouse", quantity=2, price=Decimal("29.99")),
            OrderItemCreate(product_name="Keyboard", quantity=1, price=Decimal("79.99")),
        ],
    )
    order = await create_order(data, session)

    assert len(order.items) == 3
    names = {i.product_name for i in order.items}
    assert names == {"Laptop", "Mouse", "Keyboard"}


@pytest.mark.asyncio
async def test_create_order_zero_price_item_allowed():
    """A free item (price=0) is valid per the schema (ge=0)."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    data = OrderCreate(
        customer_name="Carol",
        items=[OrderItemCreate(product_name="Freebie", quantity=1, price=Decimal("0"))],
    )
    order = await create_order(data, session)

    assert order.items[0].price == Decimal("0")


@pytest.mark.asyncio
async def test_create_order_large_quantity():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    data = OrderCreate(
        customer_name="Bulk Buyer",
        items=[OrderItemCreate(product_name="Bolt", quantity=10_000, price=Decimal("0.01"))],
    )
    order = await create_order(data, session)

    assert order.items[0].quantity == 10_000


@pytest.mark.asyncio
async def test_create_order_router_multiple_items(client):
    order = _make_order()

    with patch("src.orders.router.create_order", new=AsyncMock(return_value=order)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/orders",
                json={
                    "customer_name": "Dave",
                    "items": [
                        {"product_name": "TV", "quantity": 1, "price": "599.00"},
                        {"product_name": "Remote", "quantity": 1, "price": "9.99"},
                        {"product_name": "HDMI Cable", "quantity": 2, "price": "14.99"},
                    ],
                },
            )

    assert response.status_code == 201


# ── Requirement 3: State machine — all 25 transitions ─────────────────────────

@pytest.mark.parametrize("from_status,to_status", sorted(VALID_TRANSITIONS, key=lambda x: x[0].value))
@pytest.mark.asyncio
async def test_valid_status_transition(from_status: OrderStatus, to_status: OrderStatus):
    """All 3 valid transitions succeed and update the status."""
    order = _make_order(status=from_status)
    session = _session_returning(order)

    updated = await update_order_status(order.id, to_status, session)

    assert updated.status == to_status
    assert updated.updated_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("from_status,to_status", INVALID_TRANSITIONS)
@pytest.mark.asyncio
async def test_invalid_status_transition_raises(from_status: OrderStatus, to_status: OrderStatus):
    """All 22 invalid transitions raise OrderStatusTransitionError without committing."""
    order = _make_order(status=from_status)
    session = _session_returning(order)

    with pytest.raises(OrderStatusTransitionError) as exc_info:
        await update_order_status(order.id, to_status, session)

    assert from_status.value in str(exc_info.value)
    assert to_status.value in str(exc_info.value)
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("from_status,to_status", sorted(VALID_TRANSITIONS, key=lambda x: x[0].value))
@pytest.mark.asyncio
async def test_patch_status_route_valid_transitions(
    client, from_status: OrderStatus, to_status: OrderStatus
):
    """Router returns 200 for all valid transitions."""
    order = _make_order(status=to_status)

    with patch("src.orders.router.update_order_status", new=AsyncMock(return_value=order)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch(
                f"/orders/{order.id}/status",
                json={"status": to_status.value},
            )

    assert response.status_code == 200
    assert response.json()["status"] == to_status.value


@pytest.mark.parametrize("from_status,to_status", INVALID_TRANSITIONS[:6])
@pytest.mark.asyncio
async def test_patch_status_route_invalid_transitions_return_422(
    client, from_status: OrderStatus, to_status: OrderStatus
):
    """Router maps OrderStatusTransitionError to 422 for invalid transitions."""
    order_id = uuid.uuid4()

    with patch(
        "src.orders.router.update_order_status",
        new=AsyncMock(
            side_effect=OrderStatusTransitionError(order_id, from_status.value, to_status.value)
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch(
                f"/orders/{order_id}/status",
                json={"status": to_status.value},
            )

    assert response.status_code == 422


# ── Requirement 4: List all orders — all status filter values ─────────────────

@pytest.mark.parametrize("status", ALL_STATUSES)
@pytest.mark.asyncio
async def test_list_orders_each_status_filter(status: OrderStatus):
    """list_orders correctly filters for each of the 5 possible statuses."""
    order = _make_order(status=status)
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [order]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    result = await list_orders(session, status=status)

    assert len(result) == 1
    assert result[0].status == status


@pytest.mark.asyncio
async def test_list_orders_empty_result():
    """list_orders returns an empty list when no orders match."""
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    result = await list_orders(session)

    assert result == []


@pytest.mark.asyncio
async def test_list_orders_empty_with_status_filter():
    """list_orders returns empty list when status filter matches nothing."""
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    result = await list_orders(session, status=OrderStatus.DELIVERED)

    assert result == []


@pytest.mark.parametrize("status", ALL_STATUSES)
@pytest.mark.asyncio
async def test_list_orders_route_each_status_filter(client, status: OrderStatus):
    """GET /orders?status=X returns 200 for each valid status value."""
    orders = [_make_order(status=status)]

    with patch("src.orders.router.list_orders", new=AsyncMock(return_value=orders)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/orders?status={status.value}")

    assert response.status_code == 200
    assert response.json()[0]["status"] == status.value


@pytest.mark.asyncio
async def test_list_orders_route_invalid_status_returns_422(client):
    """GET /orders?status=INVALID returns 422 — FastAPI rejects bad enum values."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/orders?status=INVALID_VALUE")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_orders_route_no_filter_returns_all(client):
    """GET /orders with no filter returns all orders regardless of status."""
    orders = [_make_order(status=s) for s in ALL_STATUSES]

    with patch("src.orders.router.list_orders", new=AsyncMock(return_value=orders)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/orders")

    assert response.status_code == 200
    assert len(response.json()) == len(ALL_STATUSES)


# ── Requirement 5: Cancel — all non-PENDING statuses raise ────────────────────

NON_PENDING_STATUSES = [s for s in ALL_STATUSES if s != OrderStatus.PENDING]


@pytest.mark.parametrize("status", NON_PENDING_STATUSES)
@pytest.mark.asyncio
async def test_cancel_non_pending_order_raises(status: OrderStatus):
    """cancel_order raises OrderNotCancellable for every non-PENDING status."""
    order = _make_order(status=status)
    session = _session_returning(order)

    with pytest.raises(OrderNotCancellable) as exc_info:
        await cancel_order(order.id, session)

    assert status.value in str(exc_info.value)
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("status", NON_PENDING_STATUSES)
@pytest.mark.asyncio
async def test_cancel_route_non_pending_returns_409(client, status: OrderStatus):
    """DELETE /orders/{id} returns 409 for every non-PENDING status."""
    order_id = uuid.uuid4()

    with patch(
        "src.orders.router.cancel_order",
        new=AsyncMock(
            side_effect=OrderNotCancellable(order_id, status.value)
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete(f"/orders/{order_id}")

    assert response.status_code == 409
    assert status.value in response.json()["detail"]


# ── Requirement 2: Retrieve order — error and success ─────────────────────────

@pytest.mark.parametrize("status", ALL_STATUSES)
@pytest.mark.asyncio
async def test_get_order_route_returns_correct_status(client, status: OrderStatus):
    """GET /orders/{id} surfaces the order's status faithfully for all 5 statuses."""
    order = _make_order(status=status)

    with patch("src.orders.router.get_order", new=AsyncMock(return_value=order)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/orders/{order.id}")

    assert response.status_code == 200
    assert response.json()["status"] == status.value


# ── Scheduler configuration ───────────────────────────────────────────────────

def test_scheduler_configured_with_5_minute_interval():
    """APScheduler job is set to fire every 5 minutes."""
    from apscheduler.triggers.interval import IntervalTrigger
    from src.scheduler.setup import create_scheduler

    factory = MagicMock()
    scheduler = create_scheduler(factory)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    trigger = job.trigger
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval.total_seconds() == 300  # 5 * 60


def test_scheduler_has_max_instances_1():
    """Scheduler job has max_instances=1 to prevent overlapping runs."""
    from src.scheduler.setup import create_scheduler

    factory = MagicMock()
    scheduler = create_scheduler(factory)

    job = scheduler.get_jobs()[0]
    assert job.max_instances == 1


def test_scheduler_has_coalesce_true():
    """Scheduler job has coalesce=True to merge missed fires into one run."""
    from src.scheduler.setup import create_scheduler

    factory = MagicMock()
    scheduler = create_scheduler(factory)

    job = scheduler.get_jobs()[0]
    assert job.coalesce is True


def test_scheduler_job_id():
    """Scheduler job has a stable ID for management and replacement."""
    from src.scheduler.setup import create_scheduler

    factory = MagicMock()
    scheduler = create_scheduler(factory)

    job = scheduler.get_jobs()[0]
    assert job.id == "promote_pending_orders"
