from __future__ import annotations

import os
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import dotenv_values

from src.agent.tools import build_mcp_server
from src.orders.models import Order, OrderItem, OrderStatus

_env = dotenv_values(".env")
_explicit_db_url: str | None = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")

EXPECTED_TOOLS = {
    "create_order_tool",
    "get_order_tool",
    "list_orders_tool",
    "cancel_order_tool",
    "find_orders_by_product_tool",
    "search_orders",
}


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _session_factory_returning(order: Order | None):
    """Session factory whose execute() returns a single scalar result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = order
    scalars = MagicMock()
    scalars.all.return_value = [] if order is None else [order]
    result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    def factory():
        @asynccontextmanager
        async def _ctx():
            yield session
        return _ctx()
    return factory


def _make_order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    order = Order(customer_name="Test")
    import uuid
    order.id = uuid.uuid4()
    order.status = status
    item = OrderItem(product_name="Widget", quantity=1, price=Decimal("5.00"))
    item.id = uuid.uuid4()
    item.order_id = order.id
    order.items = [item]
    return order


@pytest.mark.asyncio
async def test_list_tools_contains_all_six():
    """All six MCP tools are registered — run_migrations is intentionally excluded."""
    from unittest.mock import MagicMock

    mcp = build_mcp_server(MagicMock())  # session factory not called for list_tools
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS
    assert "run_migrations" not in names


# ── Tool error paths (no DB needed) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_order_tool_invalid_uuid_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="UUID|Invalid order ID"):
        await mcp.call_tool("get_order_tool", {"order_id": "not-a-valid-uuid"})


@pytest.mark.asyncio
async def test_cancel_order_tool_invalid_uuid_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="UUID|Invalid order ID"):
        await mcp.call_tool("cancel_order_tool", {"order_id": "not-a-valid-uuid"})


@pytest.mark.asyncio
async def test_list_orders_tool_invalid_status_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="Invalid status|Must be one of"):
        await mcp.call_tool("list_orders_tool", {"status": "TOTALLY_WRONG"})


@pytest.mark.asyncio
async def test_create_order_tool_invalid_item_missing_key_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="Invalid order data|product_name|missing"):
        await mcp.call_tool(
            "create_order_tool",
            {"customer_name": "Alice", "items": [{"quantity": 1, "price": "5.00"}]},
        )


@pytest.mark.asyncio
async def test_create_order_tool_zero_quantity_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="Invalid order data|greater than"):
        await mcp.call_tool(
            "create_order_tool",
            {
                "customer_name": "Alice",
                "items": [{"product_name": "Widget", "quantity": 0, "price": "5.00"}],
            },
        )


@pytest.mark.asyncio
async def test_find_orders_by_product_tool_invalid_status_raises():
    mcp = build_mcp_server(MagicMock())
    with pytest.raises(Exception, match="Invalid status|Must be one of"):
        await mcp.call_tool(
            "find_orders_by_product_tool",
            {"product_name": "Widget", "status": "BOGUS"},
        )


# ── Tool error paths (mocked DB) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_order_tool_order_not_found_raises():
    """get_order_tool raises when the order ID is valid UUID but not in DB."""
    import uuid
    factory = _session_factory_returning(None)  # scalar_one_or_none → None → OrderNotFound
    mcp = build_mcp_server(factory)
    with pytest.raises(Exception):
        await mcp.call_tool("get_order_tool", {"order_id": str(uuid.uuid4())})


@pytest.mark.asyncio
async def test_cancel_order_tool_order_not_found_raises():
    import uuid
    factory = _session_factory_returning(None)
    mcp = build_mcp_server(factory)
    with pytest.raises(Exception):
        await mcp.call_tool("cancel_order_tool", {"order_id": str(uuid.uuid4())})


@pytest.mark.asyncio
async def test_cancel_order_tool_not_cancellable_raises():
    """cancel_order_tool raises when the order is not in PENDING status."""
    order = _make_order(status=OrderStatus.PROCESSING)
    factory = _session_factory_returning(order)
    mcp = build_mcp_server(factory)
    with pytest.raises(Exception):
        await mcp.call_tool("cancel_order_tool", {"order_id": str(order.id)})


# ── find_orders_by_product_tool happy path (mocked DB) ───────────────────────

@pytest.mark.asyncio
async def test_find_orders_by_product_tool_returns_matches():
    import json
    order = _make_order()
    factory = _session_factory_returning(order)
    mcp = build_mcp_server(factory)
    raw = await mcp.call_tool("find_orders_by_product_tool", {"product_name": "Widget"})
    # FastMCP 1.28 returns (content_items, {"result": [...]}) for list tools
    meta = raw[1] if isinstance(raw, tuple) else {}
    orders = meta.get("result", []) if isinstance(meta, dict) else json.loads(raw[0].text)
    assert isinstance(orders, list)
    assert len(orders) == 1
    assert orders[0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_find_orders_by_product_tool_no_match_returns_empty():
    factory = _session_factory_returning(None)
    mcp = build_mcp_server(factory)
    raw = await mcp.call_tool("find_orders_by_product_tool", {"product_name": "Toaster"})
    meta = raw[1] if isinstance(raw, tuple) else {}
    orders = meta.get("result", []) if isinstance(meta, dict) else []
    assert orders == []


# ── list_orders_tool happy path (mocked DB) ───────────────────────────────────

@pytest.mark.asyncio
async def test_list_orders_tool_returns_orders():
    order = _make_order()
    factory = _session_factory_returning(order)
    mcp = build_mcp_server(factory)
    raw = await mcp.call_tool("list_orders_tool", {})
    meta = raw[1] if isinstance(raw, tuple) else {}
    orders = meta.get("result", []) if isinstance(meta, dict) else []
    assert isinstance(orders, list)
    assert orders[0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_list_orders_tool_valid_status_filter_accepted():
    factory = _session_factory_returning(None)
    mcp = build_mcp_server(factory)
    raw = await mcp.call_tool("list_orders_tool", {"status": "PENDING"})
    meta = raw[1] if isinstance(raw, tuple) else {}
    orders = meta.get("result", []) if isinstance(meta, dict) else []
    assert isinstance(orders, list)


# ── End-to-end (live DB) ──────────────────────────────────────────────────────

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
