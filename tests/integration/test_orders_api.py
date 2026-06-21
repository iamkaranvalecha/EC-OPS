from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.models import Order, OrderStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

_SIMPLE_ORDER = {
    "customer_name": "Test User",
    "items": [{"product_name": "Widget", "quantity": 1, "price": "9.99"}],
}

_MULTI_ITEM_ORDER = {
    "customer_name": "Integration Tester",
    "items": [
        {"product_name": "Alpha", "quantity": 3, "price": "10.00"},
        {"product_name": "Beta", "quantity": 1, "price": "25.50"},
    ],
}


async def _force_status(
    db_session: AsyncSession, order_id: str, status: OrderStatus
) -> None:
    """Set an order's status directly in the DB, bypassing business logic."""
    result = await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id))
    )
    order = result.scalar_one()
    order.status = status
    await db_session.commit()


# ── Happy-path flow ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_get_list_cancel_flow(api_client: AsyncClient):
    create_response = await api_client.post("/orders", json=_MULTI_ITEM_ORDER)
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

    # Soft-delete: record is retained with CANCELLED status
    get_after_cancel = await api_client.get(f"/orders/{order_id}")
    assert get_after_cancel.status_code == 200
    assert get_after_cancel.json()["status"] == "CANCELLED"

    # CANCELLED orders appear in the unfiltered list
    list_after_cancel = await api_client.get("/orders")
    assert any(o["id"] == order_id for o in list_after_cancel.json())

    # CANCELLED orders appear when filtering by status=CANCELLED
    cancelled_list = await api_client.get("/orders?status=CANCELLED")
    assert any(o["id"] == order_id for o in cancelled_list.json())

    # CANCELLED order cannot be cancelled again → 409
    double_cancel = await api_client.delete(f"/orders/{order_id}")
    assert double_cancel.status_code == 409


# ── POST /orders — validation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_order_missing_customer_name_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"items": [{"product_name": "Widget", "quantity": 1, "price": "5.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_empty_customer_name_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "", "items": [{"product_name": "Widget", "quantity": 1, "price": "5.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_empty_items_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_missing_items_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_zero_quantity_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": [{"product_name": "Widget", "quantity": 0, "price": "5.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_negative_quantity_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": [{"product_name": "Widget", "quantity": -1, "price": "5.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_negative_price_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": [{"product_name": "Widget", "quantity": 1, "price": "-1.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_zero_price_is_allowed(api_client: AsyncClient):
    """Price of exactly 0 passes schema validation (ge=0)."""
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": [{"product_name": "FreeSample", "quantity": 1, "price": "0.00"}]},
    )
    assert response.status_code == 201
    assert response.json()["items"][0]["price"] == "0.00"


@pytest.mark.asyncio
async def test_create_order_empty_product_name_returns_422(api_client: AsyncClient):
    response = await api_client.post(
        "/orders",
        json={"customer_name": "Alice", "items": [{"product_name": "", "quantity": 1, "price": "5.00"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_returns_correct_fields(api_client: AsyncClient):
    """Created order response includes all required fields with correct types."""
    response = await api_client.post("/orders", json=_SIMPLE_ORDER)
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert "status" in body
    assert "created_at" in body
    assert "updated_at" in body
    assert "items" in body
    assert body["status"] == "PENDING"
    # updated_at is null on a freshly created order
    assert body["updated_at"] is None


# ── GET /orders — list ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_orders_returns_empty_when_no_orders(api_client: AsyncClient):
    response = await api_client.get("/orders")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_orders_returns_only_own_orders(
    api_client: AsyncClient, db_session: AsyncSession
):
    """List returns the created order (user_id filtering verified end-to-end)."""
    await api_client.post("/orders", json=_SIMPLE_ORDER)
    response = await api_client.get("/orders")
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 1
    assert orders[0]["customer_name"] == "Test User"


@pytest.mark.asyncio
async def test_list_orders_filter_processing(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.PROCESSING)

    response = await api_client.get("/orders?status=PROCESSING")
    assert response.status_code == 200
    assert any(o["id"] == order_id for o in response.json())

    response_pending = await api_client.get("/orders?status=PENDING")
    assert not any(o["id"] == order_id for o in response_pending.json())


@pytest.mark.asyncio
async def test_list_orders_filter_shipped(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.SHIPPED)

    response = await api_client.get("/orders?status=SHIPPED")
    assert response.status_code == 200
    assert any(o["id"] == order_id for o in response.json())


@pytest.mark.asyncio
async def test_list_orders_filter_delivered(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.DELIVERED)

    response = await api_client.get("/orders?status=DELIVERED")
    assert response.status_code == 200
    assert any(o["id"] == order_id for o in response.json())


@pytest.mark.asyncio
async def test_list_orders_invalid_status_returns_422(api_client: AsyncClient):
    response = await api_client.get("/orders?status=INVALID")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_orders_pending_does_not_include_cancelled(
    api_client: AsyncClient
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await api_client.delete(f"/orders/{order_id}")

    response = await api_client.get("/orders?status=PENDING")
    assert not any(o["id"] == order_id for o in response.json())


# ── GET /orders/{id} ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_nonexistent_order_returns_404(api_client: AsyncClient):
    response = await api_client.get(f"/orders/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_order_invalid_uuid_returns_422(api_client: AsyncClient):
    response = await api_client.get("/orders/not-a-valid-uuid")
    assert response.status_code == 422


# ── DELETE /orders/{id} — cancel ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_non_pending_order_returns_409(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.PROCESSING)

    response = await api_client.delete(f"/orders/{order_id}")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cancel_shipped_order_returns_409(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.SHIPPED)

    response = await api_client.delete(f"/orders/{order_id}")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cancel_delivered_order_returns_409(
    api_client: AsyncClient, db_session: AsyncSession
):
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]
    await _force_status(db_session, order_id, OrderStatus.DELIVERED)

    response = await api_client.delete(f"/orders/{order_id}")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cancel_nonexistent_order_returns_404(api_client: AsyncClient):
    response = await api_client.delete(f"/orders/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_order_invalid_uuid_returns_422(api_client: AsyncClient):
    response = await api_client.delete("/orders/not-a-valid-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cancel_returns_no_body(api_client: AsyncClient):
    """DELETE /orders/{id} returns 204 with no response body."""
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    order_id = r.json()["id"]

    response = await api_client.delete(f"/orders/{order_id}")
    assert response.status_code == 204
    assert response.content == b""


# ── Cross-user isolation ──────────────────────────────────────────────────────
#
# These tests verify that user_id scoping is enforced end-to-end through
# router → service → SQL. A second user is registered within the test using
# the same injected session so both users' data shares the same transaction.

@pytest.mark.asyncio
async def test_user_cannot_get_another_users_order(api_client: AsyncClient):
    """GET /orders/{id} returns 404 (not 403) for an order owned by another user."""
    # Create order as fixture user (testuser)
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    assert r.status_code == 201
    order_id = r.json()["id"]

    # Register + login as a second user (reuses same injected session via app.dependency_overrides)
    await api_client.post("/auth/register", json={"username": "user2_get", "password": "Password1!"})
    token_resp = await api_client.post(
        "/auth/token", data={"username": "user2_get", "password": "Password1!"}
    )
    user2_token = token_resp.json()["access_token"]

    # Attempt to fetch testuser's order as user2
    response = await api_client.get(
        f"/orders/{order_id}",
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_list_another_users_orders(api_client: AsyncClient):
    """GET /orders returns an empty list for a user who has no orders."""
    # Create order as testuser
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    assert r.status_code == 201

    # Register + login as user2
    await api_client.post("/auth/register", json={"username": "user2_list", "password": "Password1!"})
    token_resp = await api_client.post(
        "/auth/token", data={"username": "user2_list", "password": "Password1!"}
    )
    user2_token = token_resp.json()["access_token"]

    # user2 lists orders — must see nothing (testuser's order is invisible)
    response = await api_client.get(
        "/orders",
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_user_cannot_cancel_another_users_order(api_client: AsyncClient):
    """DELETE /orders/{id} returns 404 when the order belongs to another user."""
    # Create order as testuser
    r = await api_client.post("/orders", json=_SIMPLE_ORDER)
    assert r.status_code == 201
    order_id = r.json()["id"]

    # Register + login as user2
    await api_client.post("/auth/register", json={"username": "user2_cancel", "password": "Password1!"})
    token_resp = await api_client.post(
        "/auth/token", data={"username": "user2_cancel", "password": "Password1!"}
    )
    user2_token = token_resp.json()["access_token"]

    # user2 attempts to cancel testuser's order
    response = await api_client.delete(
        f"/orders/{order_id}",
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert response.status_code == 404

    # Verify the order still exists and is still PENDING for testuser
    verify = await api_client.get(f"/orders/{order_id}")
    assert verify.status_code == 200
    assert verify.json()["status"] == "PENDING"


# ── Auth enforcement on orders routes ────────────────────────────────────────

@pytest.mark.asyncio
async def test_orders_routes_require_auth(raw_client: AsyncClient):
    """Every orders endpoint rejects unauthenticated requests with 401."""
    fake_id = uuid.uuid4()
    assert (await raw_client.get("/orders")).status_code == 401
    assert (await raw_client.post("/orders", json=_SIMPLE_ORDER)).status_code == 401
    assert (await raw_client.get(f"/orders/{fake_id}")).status_code == 401
    assert (await raw_client.delete(f"/orders/{fake_id}")).status_code == 401
