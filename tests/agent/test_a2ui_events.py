from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.events import UiAction


@pytest.mark.asyncio
async def test_ui_action_emitted_after_order_tool_call():
    """A ui_action CustomEvent is emitted after a ToolCallResult with an order payload."""
    from src.agent.agui_stream import stream_executor

    order_payload = {"id": "abc-123", "customer_name": "Alice", "status": "PENDING"}
    order_json = json.dumps(order_payload)

    mock_tool = MagicMock()
    mock_tool.name = "create_order_tool"
    mock_tool.description = "Create order"
    mock_tool.inputSchema = {}

    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(return_value=[mock_tool])

    # Anthropic: first turn returns tool_use, second returns end_turn
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-001"
    tool_block.name = "create_order_tool"
    tool_block.input = {}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Order created."

    first_response = MagicMock()
    first_response.stop_reason = "tool_use"
    first_response.content = [tool_block]

    second_response = MagicMock()
    second_response.stop_reason = "end_turn"
    second_response.content = [text_block]

    # Build two streaming context managers
    def make_stream_ctx(response):
        ctx = MagicMock()
        # __aiter__ yields nothing (no streaming text deltas in this test)
        async def aiter():
            return
            yield  # makes it an async generator

        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.__aiter__ = lambda self: aiter()
        ctx.get_final_message = AsyncMock(return_value=response)
        return ctx

    stream_responses = [make_stream_ctx(first_response), make_stream_ctx(second_response)]
    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = stream_responses

    # MCP call_tool returns the order JSON as TextContent
    mock_content = MagicMock()
    mock_content.text = order_json
    mock_mcp.call_tool = AsyncMock(return_value=[mock_content])

    with patch("src.agent.agui_stream.build_mcp_server", return_value=mock_mcp):
        events = []
        async for event in stream_executor(
            "Create an order", MagicMock(), anthropic_client=mock_client
        ):
            events.append(json.loads(event["data"]))

    types = [e["type"] for e in events]
    assert "CustomEvent" in types

    ui_events = [e for e in events if e["type"] == "CustomEvent" and e.get("name") == "ui_action"]
    assert len(ui_events) == 1
    assert ui_events[0]["value"]["action"] == "order_card"
    assert ui_events[0]["value"]["payload"]["id"] == "abc-123"
    assert ui_events[0]["value"]["payload"]["customer_name"] == "Alice"


@pytest.mark.asyncio
async def test_ui_action_not_emitted_for_non_order_result():
    """No ui_action is emitted when the tool result is not a JSON object with an id."""
    from src.agent.agui_stream import stream_executor

    mock_tool = MagicMock()
    mock_tool.name = "cancel_order_tool"
    mock_tool.description = "Cancel"
    mock_tool.inputSchema = {}

    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(return_value=[mock_tool])

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-002"
    tool_block.name = "cancel_order_tool"
    tool_block.input = {}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Cancelled."

    first_response = MagicMock()
    first_response.stop_reason = "tool_use"
    first_response.content = [tool_block]

    second_response = MagicMock()
    second_response.stop_reason = "end_turn"
    second_response.content = [text_block]

    def make_stream_ctx(response):
        ctx = MagicMock()
        async def aiter():
            return
            yield
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.__aiter__ = lambda self: aiter()
        ctx.get_final_message = AsyncMock(return_value=response)
        return ctx

    stream_responses = [make_stream_ctx(first_response), make_stream_ctx(second_response)]
    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = stream_responses

    # Tool returns plain string "cancelled" (not a JSON object with id)
    mock_content = MagicMock()
    mock_content.text = "cancelled"
    mock_mcp.call_tool = AsyncMock(return_value=[mock_content])

    with patch("src.agent.agui_stream.build_mcp_server", return_value=mock_mcp):
        events = []
        async for event in stream_executor(
            "Cancel order", MagicMock(), anthropic_client=mock_client
        ):
            events.append(json.loads(event["data"]))

    ui_events = [e for e in events if e.get("type") == "CustomEvent"]
    assert len(ui_events) == 0


@pytest.mark.asyncio
async def test_ui_action_not_emitted_for_non_whitelisted_tool_returning_id():
    """No ui_action is emitted when a non-order tool returns a JSON dict with an id field."""
    from src.agent.agui_stream import stream_executor

    mock_tool = MagicMock()
    mock_tool.name = "future_tool"
    mock_tool.description = "Future"
    mock_tool.inputSchema = {}

    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(return_value=[mock_tool])

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tc-003"
    tool_block.name = "future_tool"
    tool_block.input = {}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Done."

    first_response = MagicMock()
    first_response.stop_reason = "tool_use"
    first_response.content = [tool_block]

    second_response = MagicMock()
    second_response.stop_reason = "end_turn"
    second_response.content = [text_block]

    def make_stream_ctx(response):
        ctx = MagicMock()
        async def aiter():
            return
            yield
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.__aiter__ = lambda self: aiter()
        ctx.get_final_message = AsyncMock(return_value=response)
        return ctx

    stream_responses = [make_stream_ctx(first_response), make_stream_ctx(second_response)]
    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = stream_responses

    # Non-whitelisted tool returns a JSON dict that contains "id" — should NOT emit ui_action
    mock_content = MagicMock()
    mock_content.text = json.dumps({"id": "some-id", "value": 42})
    mock_mcp.call_tool = AsyncMock(return_value=[mock_content])

    with patch("src.agent.agui_stream.build_mcp_server", return_value=mock_mcp):
        events = []
        async for event in stream_executor(
            "Do something", MagicMock(), anthropic_client=mock_client
        ):
            events.append(json.loads(event["data"]))

    ui_events = [e for e in events if e.get("type") == "CustomEvent"]
    assert len(ui_events) == 0


@pytest.mark.asyncio
async def test_ui_action_event_schema():
    """UiAction.to_sse() produces correct JSON schema with type, name, value."""
    action = UiAction(payload={"id": "x", "status": "PENDING"})
    data = json.loads(action.to_sse())
    assert data["type"] == "CustomEvent"
    assert data["name"] == "ui_action"
    assert data["value"]["action"] == "order_card"
    assert data["value"]["payload"]["id"] == "x"
