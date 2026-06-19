from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.executor import ExecutionResult
from src.main import app


@pytest.mark.asyncio
async def test_agent_card_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/.well-known/agent.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "EC-OPS Order Agent"
    assert "skills" in body
    assert len(body["skills"]) == 4


@pytest.mark.asyncio
async def test_send_task_returns_202_pending_then_completed():
    mock_result = ExecutionResult(
        text="Order created successfully.",
        tool_calls=[{"name": "create_order_tool", "input": {}, "output": "{}"}],
    )
    with patch("src.agent.a2a_router.run_executor", new=AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/a2a/tasks/send", json={"message": "Create an order"})
            assert response.status_code == 202
            body = response.json()
            assert "id" in body
            assert body["status"] == "pending"
            task_id = body["id"]

            # Yield to let the background task run
            await asyncio.sleep(0)

            get_resp = await ac.get(f"/a2a/tasks/{task_id}")
    assert get_resp.status_code == 200
    completed = get_resp.json()
    assert completed["status"] == "completed"
    assert completed["result"]["text"] == "Order created successfully."


@pytest.mark.asyncio
async def test_get_task_returns_task():
    mock_result = ExecutionResult(text="Done.", tool_calls=[])
    with patch("src.agent.a2a_router.run_executor", new=AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            post_resp = await ac.post("/a2a/tasks/send", json={"message": "List orders"})
            task_id = post_resp.json()["id"]
            await asyncio.sleep(0)
            get_resp = await ac.get(f"/a2a/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id


@pytest.mark.asyncio
async def test_get_task_404_for_unknown():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/a2a/tasks/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_task_marks_failed_on_executor_error():
    with patch(
        "src.agent.a2a_router.run_executor",
        new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/a2a/tasks/send", json={"message": "anything"})
            assert response.status_code == 202
            assert response.json()["status"] == "pending"
            task_id = response.json()["id"]

            await asyncio.sleep(0)

            get_resp = await ac.get(f"/a2a/tasks/{task_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["status"] == "failed"
    assert "LLM unavailable" in body["error"]


@pytest.mark.asyncio
async def test_get_failed_task_has_error_field():
    with patch(
        "src.agent.a2a_router.run_executor",
        new=AsyncMock(side_effect=ValueError("tool error")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            post_resp = await ac.post("/a2a/tasks/send", json={"message": "do something"})
            task_id = post_resp.json()["id"]
            await asyncio.sleep(0)
            get_resp = await ac.get(f"/a2a/tasks/{task_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["status"] == "failed"
    assert body["error"] is not None
    assert "tool error" in body["error"]
    assert body["result"] is None
