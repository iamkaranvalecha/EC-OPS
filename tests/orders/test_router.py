from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.dependencies import get_session
from src.main import app
from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import Order, OrderItem, OrderStatus


def _make_order(
    status: OrderStatus = OrderStatus.PENDING,
    customer_name: str = "Alice",
) -> Order:
    order = Order(customer_name=customer_name)
    order.id = uuid.uuid4()
    order.status = status
    order.created_at = datetime.now(timezone.utc)
    order.updated_at = None
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


@pytest.fixture
def mock_session():
    return _mock_session()


@pytest.fixture
def client(mock_session):
    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_orders_returns_201(client, mock_session):
    order = _make_order()

    with patch("src.orders.router.create_order", new=AsyncMock(return_value=order)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/orders",
                json={
                    "customer_name": "Alice",
                    "items": [
                        {"product_name": "Widget", "quantity": 2, "price": "5.00"}
                    ],
                },
            )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(order.id)
    assert body["customer_name"] == "Alice"
    assert body["status"] == "PENDING"
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_get_order_by_id_returns_200(client, mock_session):
    order = _make_order()

    with patch("src.orders.router.get_order", new=AsyncMock(return_value=order)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/orders/{order.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(order.id)


@pytest.mark.asyncio
async def test_get_order_by_id_returns_404_when_not_found(client, mock_session):
    order_id = uuid.uuid4()

    with patch(
        "src.orders.router.get_order",
        new=AsyncMock(side_effect=OrderNotFound(order_id)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/orders/{order_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_orders_list_returns_200(client, mock_session):
    orders = [_make_order(), _make_order(status=OrderStatus.PROCESSING, customer_name="Bob")]

    with patch("src.orders.router.list_orders", new=AsyncMock(return_value=orders)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/orders")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


@pytest.mark.asyncio
async def test_get_orders_list_with_status_filter(client, mock_session):
    pending = _make_order(status=OrderStatus.PENDING)

    mock_list = AsyncMock(return_value=[pending])
    with patch("src.orders.router.list_orders", new=mock_list):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/orders?status=PENDING")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "PENDING"
    mock_list.assert_called_once_with(mock_session, status=OrderStatus.PENDING)


@pytest.mark.asyncio
async def test_delete_order_returns_204_on_pending(client, mock_session):
    order_id = uuid.uuid4()

    with patch("src.orders.router.cancel_order", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete(f"/orders/{order_id}")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_order_returns_409_when_not_cancellable(client, mock_session):
    order_id = uuid.uuid4()

    with patch(
        "src.orders.router.cancel_order",
        new=AsyncMock(side_effect=OrderNotCancellable(order_id, "PROCESSING")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete(f"/orders/{order_id}")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_order_returns_404_when_not_found(client, mock_session):
    order_id = uuid.uuid4()

    with patch(
        "src.orders.router.cancel_order",
        new=AsyncMock(side_effect=OrderNotFound(order_id)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.delete(f"/orders/{order_id}")

    assert response.status_code == 404
