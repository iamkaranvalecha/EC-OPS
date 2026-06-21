"""
Verify that agent and A2A routes enforce JWT authentication.

These tests live in tests/auth/ intentionally — the tests/agent/conftest.py
has autouse=True bypass_auth that would mask 401 responses for any test in
tests/agent/. Here we want real auth enforcement.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import _resolve_token
from src.auth.service import create_access_token
from src.main import app


@pytest.mark.asyncio
async def test_agent_stream_no_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agent/stream?message=list+orders")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_stream_invalid_token_returns_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer not.a.valid.token"},
    ) as ac:
        resp = await ac.get("/agent/stream?message=list+orders")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_stream_token_as_query_param_no_valid_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/agent/stream?message=list+orders&token=not.a.valid.token")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a2a_send_task_no_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/a2a/tasks/send", json={"message": "list orders"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a2a_send_task_invalid_token_returns_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer garbage.token.here"},
    ) as ac:
        resp = await ac.post("/a2a/tasks/send", json={"message": "list orders"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a2a_get_task_no_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/a2a/tasks/some-task-id")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_card_no_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/.well-known/agent.json")
    assert resp.status_code == 401


# ── _resolve_token unit tests ─────────────────────────────────────────────────
# Test the extraction logic directly so a change to the header-vs-query-param
# fallback path is caught without needing a full HTTP roundtrip.

@pytest.mark.asyncio
async def test_resolve_token_from_bearer_header():
    token = create_access_token(uuid.uuid4(), "testuser")
    result = await _resolve_token(authorization=f"Bearer {token}", token=None)
    assert result == token


@pytest.mark.asyncio
async def test_resolve_token_from_query_param():
    """Browser EventSource clients send the token as ?token= because they cannot set headers."""
    token = create_access_token(uuid.uuid4(), "testuser")
    result = await _resolve_token(authorization=None, token=token)
    assert result == token


@pytest.mark.asyncio
async def test_resolve_token_header_takes_precedence_over_query():
    header_token = create_access_token(uuid.uuid4(), "user_header")
    query_token = create_access_token(uuid.uuid4(), "user_query")
    result = await _resolve_token(
        authorization=f"Bearer {header_token}", token=query_token
    )
    assert result == header_token


@pytest.mark.asyncio
async def test_resolve_token_raises_401_when_neither_present():
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_token(authorization=None, token=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_resolve_token_raises_401_for_non_bearer_header():
    """Authorization header without 'Bearer ' prefix is ignored, falls through to 401."""
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_token(authorization="Basic dXNlcjpwYXNz", token=None)
    assert exc_info.value.status_code == 401
