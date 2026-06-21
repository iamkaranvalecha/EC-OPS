from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport
from httpx import AsyncClient as RawClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.service import create_access_token
from src.main import app


@pytest.mark.asyncio
async def test_register_success(raw_client: RawClient):
    """POST /auth/register creates a new user and returns 201."""
    response = await raw_client.post(
        "/auth/register",
        json={"username": "newuser", "password": "Password1!"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "newuser"
    assert body["is_active"] is True
    assert "id" in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_duplicate_username(raw_client: RawClient):
    """Registering the same username twice returns 409."""
    await raw_client.post("/auth/register", json={"username": "dupuser", "password": "Password1!"})
    response = await raw_client.post(
        "/auth/register",
        json={"username": "dupuser", "password": "AnotherPass1!"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_short_password(raw_client: RawClient):
    """Passwords shorter than 8 characters return 422."""
    response = await raw_client.post(
        "/auth/register",
        json={"username": "shortpwuser", "password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(raw_client: RawClient):
    """POST /auth/token returns a JWT for valid credentials."""
    await raw_client.post(
        "/auth/register",
        json={"username": "loginuser", "password": "Password1!"},
    )
    response = await raw_client.post(
        "/auth/token",
        data={"username": "loginuser", "password": "Password1!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_wrong_password(raw_client: RawClient):
    """Wrong password returns 401."""
    await raw_client.post(
        "/auth/register",
        json={"username": "badpwuser", "password": "Password1!"},
    )
    response = await raw_client.post(
        "/auth/token",
        data={"username": "badpwuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token():
    """Requests without a Bearer token are rejected with 401."""
    async with RawClient(transport=ASGITransport(app=app), base_url="http://test") as raw:
        response = await raw.get("/orders")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_invalid_token():
    """A garbage token returns 401."""
    async with RawClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer not.a.real.token"},
    ) as raw:
        response = await raw.get("/orders")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_is_public():
    """/health requires no auth."""
    async with RawClient(transport=ASGITransport(app=app), base_url="http://test") as raw:
        response = await raw.get("/health")
    assert response.status_code == 200


# ── Username validation ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_username_too_short_returns_422(raw_client: RawClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "ab", "password": "Password1!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_username_special_chars_returns_422(raw_client: RawClient):
    """Username with @ returns 422 — only letters, digits, hyphens, underscores allowed."""
    response = await raw_client.post(
        "/auth/register",
        json={"username": "user@name", "password": "Password1!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_username_with_hyphen_and_underscore_is_allowed(raw_client: RawClient):
    response = await raw_client.post(
        "/auth/register",
        json={"username": "user_name-ok", "password": "Password1!"},
    )
    assert response.status_code == 201


# ── Login edge cases ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_nonexistent_username_returns_401(raw_client: RawClient):
    response = await raw_client.post(
        "/auth/token",
        data={"username": "doesnotexist_xyz", "password": "Password1!"},
    )
    assert response.status_code == 401


# ── Deactivated user ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivated_user_with_valid_jwt_returns_401(
    raw_client: RawClient, db_session: AsyncSession
):
    """A valid JWT for a deactivated user must be rejected at every protected route."""
    reg = await raw_client.post(
        "/auth/register",
        json={"username": "deactivated_usr", "password": "Password1!"},
    )
    assert reg.status_code == 201
    user_id = uuid.UUID(reg.json()["id"])

    await db_session.execute(
        update(User).where(User.id == user_id).values(is_active=False)
    )
    await db_session.commit()

    token = create_access_token(user_id, "deactivated_usr")
    resp = await raw_client.get("/orders", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_user_cannot_login(
    raw_client: RawClient, db_session: AsyncSession
):
    """Login endpoint returns 401 for a deactivated account even with correct credentials."""
    await raw_client.post(
        "/auth/register",
        json={"username": "deactivated_login", "password": "Password1!"},
    )
    result = await db_session.execute(
        update(User).where(User.username == "deactivated_login").values(is_active=False)
    )
    await db_session.commit()

    resp = await raw_client.post(
        "/auth/token",
        data={"username": "deactivated_login", "password": "Password1!"},
    )
    assert resp.status_code == 401
