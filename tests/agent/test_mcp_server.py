from __future__ import annotations

import os

import pytest
from dotenv import dotenv_values

from src.agent.tools import build_mcp_server

_env = dotenv_values(".env")
_explicit_db_url: str | None = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")

EXPECTED_TOOLS = {
    "create_order_tool",
    "get_order_tool",
    "list_orders_tool",
    "cancel_order_tool",
    "search_orders",
}


@pytest.mark.asyncio
async def test_list_tools_contains_all_five():
    """All five MCP tools are registered — no DB needed."""
    from unittest.mock import MagicMock

    mcp = build_mcp_server(MagicMock())  # session factory not called for list_tools
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


@pytest.mark.skipif(
    not _explicit_db_url,
    reason="requires live DB — set TEST_DATABASE_URL in .env or environment",
)
@pytest.mark.asyncio
async def test_create_order_tool_end_to_end(session_factory):
    """create_order_tool creates a real order in the test DB."""
    import uuid

    from sqlalchemy import select

    from src.orders.models import Order

    mcp = build_mcp_server(session_factory)

    import json

    content = await mcp.call_tool(
        "create_order_tool",
        {
            "customer_name": "MCP Tester",
            "items": [{"product_name": "Widget", "quantity": 2, "price": "9.99"}],
        },
    )
    result = json.loads(content[0].text)
    assert result["customer_name"] == "MCP Tester"
    assert result["status"] == "PENDING"
    assert len(result["items"]) == 1
    order_id = result["id"]

    # Verify in DB
    async with session_factory() as session:
        row = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id))
        )
        order = row.scalar_one()
    assert order.customer_name == "MCP Tester"
