"""Integration tests for auth routes — POST /auth/register and POST /auth/token.

These tests run through the full FastAPI app stack with a real (test) database,
verifying that auth works end-to-end and that JWT tokens obtained here can
be used to access protected order routes.

Requires TEST_DATABASE_URL — skipped automatically if no DB is configured.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ── Register ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_returns_201_with_user_object(raw_client: AsyncClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "int_reg_success", "password": "Password1!"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "int_reg_success"
    assert body["is_active"] is True
    assert "id" in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_duplicate_username_returns_409(raw_client: AsyncClient):
    await raw_client.post("/auth/register", json={"username": "int_dup", "password": "Password1!"})
    response = await raw_client.post(
        "/auth/register",
        json={"username": "int_dup", "password": "AnotherPass1!"},
    )
    assert response.status_code == 409
    assert "int_dup" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_short_password_returns_422(raw_client: AsyncClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "int_shortpw", "password": "abc"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_username_too_short_returns_422(raw_client: AsyncClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "ab", "password": "Password1!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_username_with_special_chars_returns_422(raw_client: AsyncClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "user@name", "password": "Password1!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_username_returns_422(raw_client: AsyncClient):
    response = await raw_client.post("/auth/register", json={"password": "Password1!"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_password_returns_422(raw_client: AsyncClient):
    response = await raw_client.post("/auth/register", json={"username": "int_nopw"})
    assert response.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_bearer_token(raw_client: AsyncClient):
    await raw_client.post("/auth/register", json={"username": "int_login_ok", "password": "Password1!"})
    response = await raw_client.post(
        "/auth/token",
        data={"username": "int_login_ok", "password": "Password1!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(raw_client: AsyncClient):
    await raw_client.post("/auth/register", json={"username": "int_wrongpw", "password": "Password1!"})
    response = await raw_client.post(
        "/auth/token",
        data={"username": "int_wrongpw", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_returns_401(raw_client: AsyncClient):
    response = await raw_client.post(
        "/auth/token",
        data={"username": f"nobody_{uuid.uuid4().hex[:8]}", "password": "Password1!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_missing_credentials_returns_422(raw_client: AsyncClient):
    response = await raw_client.post("/auth/token", data={})
    assert response.status_code == 422


# ── Full auth workflow: register → login → access orders ─────────────────────

@pytest.mark.asyncio
async def test_register_login_then_create_order(raw_client: AsyncClient):
    """End-to-end: register, obtain JWT, create an order — verifies auth is wired."""
    reg = await raw_client.post(
        "/auth/register",
        json={"username": "int_e2e_user", "password": "Password1!"},
    )
    assert reg.status_code == 201

    tok = await raw_client.post(
        "/auth/token",
        data={"username": "int_e2e_user", "password": "Password1!"},
    )
    assert tok.status_code == 200
    token = tok.json()["access_token"]

    order_resp = await raw_client.post(
        "/orders",
        json={
            "customer_name": "E2E Tester",
            "items": [{"product_name": "Widget", "quantity": 1, "price": "9.99"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert order_resp.status_code == 201
    assert order_resp.json()["customer_name"] == "E2E Tester"
    assert order_resp.json()["status"] == "PENDING"


@pytest.mark.asyncio
async def test_token_isolates_orders_between_users(raw_client: AsyncClient):
    """Two users register, each creates an order; each can only see their own."""
    for username in ("int_user_a", "int_user_b"):
        await raw_client.post(
            "/auth/register",
            json={"username": username, "password": "Password1!"},
        )

    def _login(username: str):
        return raw_client.post("/auth/token", data={"username": username, "password": "Password1!"})

    tok_a = (await _login("int_user_a")).json()["access_token"]
    tok_b = (await _login("int_user_b")).json()["access_token"]

    await raw_client.post(
        "/orders",
        json={"customer_name": "User A", "items": [{"product_name": "A Item", "quantity": 1, "price": "1.00"}]},
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    await raw_client.post(
        "/orders",
        json={"customer_name": "User B", "items": [{"product_name": "B Item", "quantity": 1, "price": "2.00"}]},
        headers={"Authorization": f"Bearer {tok_b}"},
    )

    orders_a = (await raw_client.get("/orders", headers={"Authorization": f"Bearer {tok_a}"})).json()
    orders_b = (await raw_client.get("/orders", headers={"Authorization": f"Bearer {tok_b}"})).json()

    assert len(orders_a) == 1
    assert orders_a[0]["customer_name"] == "User A"
    assert len(orders_b) == 1
    assert orders_b[0]["customer_name"] == "User B"


@pytest.mark.asyncio
async def test_invalid_token_rejected_on_every_orders_route(raw_client: AsyncClient):
    """A garbage JWT is rejected with 401 on all order endpoints."""
    bad_headers = {"Authorization": "Bearer this.is.not.valid"}
    fake_id = uuid.uuid4()
    assert (await raw_client.get("/orders", headers=bad_headers)).status_code == 401
    assert (await raw_client.post("/orders", json={}, headers=bad_headers)).status_code == 401
    assert (await raw_client.get(f"/orders/{fake_id}", headers=bad_headers)).status_code == 401
    assert (await raw_client.patch(f"/orders/{fake_id}/status", json={"status": "PROCESSING"}, headers=bad_headers)).status_code == 401
    assert (await raw_client.delete(f"/orders/{fake_id}", headers=bad_headers)).status_code == 401


# ── Public endpoints ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_is_public(raw_client: AsyncClient):
    """/health must be reachable without any auth token."""
    response = await raw_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_register_is_public(raw_client: AsyncClient):
    """/auth/register must be reachable without a token (it's how you get one)."""
    response = await raw_client.post(
        "/auth/register",
        json={"username": "int_public_check", "password": "Password1!"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_auth_token_is_public(raw_client: AsyncClient):
    """/auth/token must be reachable without a token (it's how you get one)."""
    await raw_client.post("/auth/register", json={"username": "int_public_tok", "password": "Password1!"})
    response = await raw_client.post("/auth/token", data={"username": "int_public_tok", "password": "Password1!"})
    assert response.status_code == 200
