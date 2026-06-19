from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import dotenv_values

from src.agent.executor import ExecutionResult

_env = dotenv_values(".env")
_explicit_db_url: str | None = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not _explicit_db_url,
    reason="requires live DB — set TEST_DATABASE_URL in .env or environment",
)
@pytest.mark.asyncio
async def test_create_order_task_end_to_end(api_client, session_factory):
    """Send a task message; mock executor calls create_order_tool; verify order in DB."""
    from sqlalchemy import select

    from src.agent.tools import build_mcp_server
    from src.orders.models import Order

    # Build a real MCP server against the test DB, then call the tool manually
    # to simulate what the executor would do
    mcp = build_mcp_server(session_factory)
    tool_output = await mcp.call_tool(
        "create_order_tool",
        {
            "customer_name": "A2A Tester",
            "items": [{"product_name": "Gadget", "quantity": 1, "price": "19.99"}],
        },
    )
    import json as _json
    order_data = _json.loads(tool_output[0].text)
    order_id = order_data["id"]

    # Simulate the executor returning this tool call result
    mock_result = ExecutionResult(
        text=f"Order {order_id} created for A2A Tester.",
        tool_calls=[
            {
                "name": "create_order_tool",
                "input": {
                    "customer_name": "A2A Tester",
                    "items": [{"product_name": "Gadget", "quantity": 1, "price": "19.99"}],
                },
                "output": tool_output[0].text,
            }
        ],
    )

    with patch("src.agent.a2a_router.run_executor", new=AsyncMock(return_value=mock_result)):
        response = await api_client.post(
            "/a2a/tasks/send", json={"message": "Create an order for A2A Tester"}
        )
        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        task_id_sent = response.json()["id"]

        await asyncio.sleep(0)

        get_response = await api_client.get(f"/a2a/tasks/{task_id_sent}")

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["status"] == "completed"
    assert order_id in body["result"]["text"]

    # Verify the order actually exists in the DB (the tool call above already created it)
    async with session_factory() as session:
        row = await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
        order = row.scalar_one()
    assert order.customer_name == "A2A Tester"
