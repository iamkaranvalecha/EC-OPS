from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.models import Order, OrderStatus


@pytest.mark.asyncio
async def test_create_get_list_cancel_flow(api_client: AsyncClient):
    create_response = await api_client.post(
        "/orders",
        json={
            "customer_name": "Integration Tester",
            "items": [
                {"product_name": "Alpha", "quantity": 3, "price": "10.00"},
                {"product_name": "Beta", "quantity": 1, "price": "25.50"},
            ],
        },
    )
    assert create_response.status_code == 201
    order = create_response.json()
    order_id = order["id"]
    assert order["customer_name"] == "Integration Tester"
    assert order["status"] == "PENDING"
    assert len(order["items"]) == 2

    get_response = await api_client.get(f"/orders/{order_id}")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == order_id
    assert fetched["customer_name"] == "Integration Tester"

    list_response = await api_client.get("/orders")
    assert list_response.status_code == 200
    all_orders = list_response.json()
    assert any(o["id"] == order_id for o in all_orders)

    filtered_response = await api_client.get("/orders?status=PENDING")
    assert filtered_response.status_code == 200
    pending_orders = filtered_response.json()
    assert any(o["id"] == order_id for o in pending_orders)

    cancel_response = await api_client.delete(f"/orders/{order_id}")
    assert cancel_response.status_code == 204

    get_after_cancel = await api_client.get(f"/orders/{order_id}")
    assert get_after_cancel.status_code == 404


@pytest.mark.asyncio
async def test_cancel_non_pending_order_returns_409(
    api_client: AsyncClient, db_session: AsyncSession
):
    create_response = await api_client.post(
        "/orders",
        json={
            "customer_name": "Status Tester",
            "items": [{"product_name": "Gamma", "quantity": 1, "price": "5.00"}],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    result = await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id))
    )
    db_order = result.scalar_one()
    db_order.status = OrderStatus.PROCESSING
    await db_session.commit()

    cancel_response = await api_client.delete(f"/orders/{order_id}")
    assert cancel_response.status_code == 409


@pytest.mark.asyncio
async def test_get_nonexistent_order_returns_404(api_client: AsyncClient):
    fake_id = uuid.uuid4()
    response = await api_client.get(f"/orders/{fake_id}")
    assert response.status_code == 404
