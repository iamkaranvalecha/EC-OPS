from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.events import RunFinished, RunStarted, TextDelta, ToolCallResult, ToolCallStart
from src.main import app


@pytest.mark.asyncio
async def test_stream_responds_with_event_stream_content_type():
    """GET /agent/stream returns text/event-stream content type."""
    async def mock_stream(*args, **kwargs):
        yield {"data": RunStarted().to_sse()}
        yield {"data": RunFinished().to_sse()}

    with patch("src.agent.agui_stream.stream_executor", side_effect=mock_stream):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            async with ac.stream("GET", "/agent/stream?message=test") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_stream_emits_run_started_and_finished():
    """Stream always begins with RunStarted and ends with RunFinished."""
    async def mock_stream(*args, **kwargs):
        yield {"data": RunStarted().to_sse()}
        yield {"data": RunFinished().to_sse()}

    with patch("src.agent.agui_stream.stream_executor", side_effect=mock_stream):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            async with ac.stream("GET", "/agent/stream?message=test") as response:
                body = await response.aread()

    lines = [line for line in body.decode().splitlines() if line.startswith("data:")]
    events = [json.loads(line.removeprefix("data:").strip()) for line in lines]
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"


@pytest.mark.asyncio
async def test_stream_emits_ordered_event_types():
    """Full event sequence: RunStarted, TextDelta, ToolCallStart, ToolCallResult, RunFinished."""
    tc_id = "tc-001"

    async def mock_stream(*args, **kwargs):
        yield {"data": RunStarted().to_sse()}
        yield {"data": TextDelta(delta="Processing").to_sse()}
        yield {"data": ToolCallStart(tool_name="list_orders_tool", tool_call_id=tc_id).to_sse()}
        yield {"data": ToolCallResult(tool_call_id=tc_id, result="[]").to_sse()}
        yield {"data": RunFinished().to_sse()}

    with patch("src.agent.agui_stream.stream_executor", side_effect=mock_stream):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            async with ac.stream("GET", "/agent/stream?message=list") as response:
                body = await response.aread()

    lines = [line for line in body.decode().splitlines() if line.startswith("data:")]
    events = [json.loads(line.removeprefix("data:").strip()) for line in lines]
    types = [e["type"] for e in events]
    assert types == ["RunStarted", "TextDelta", "ToolCallStart", "ToolCallResult", "RunFinished"]


@pytest.mark.asyncio
async def test_stream_text_delta_carries_content():
    """TextDelta events carry the expected delta text."""
    async def mock_stream(*args, **kwargs):
        yield {"data": RunStarted().to_sse()}
        yield {"data": TextDelta(delta="Hello world").to_sse()}
        yield {"data": RunFinished().to_sse()}

    with patch("src.agent.agui_stream.stream_executor", side_effect=mock_stream):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            async with ac.stream("GET", "/agent/stream?message=hi") as response:
                body = await response.aread()

    lines = [line for line in body.decode().splitlines() if line.startswith("data:")]
    events = [json.loads(line.removeprefix("data:").strip()) for line in lines]
    text_deltas = [e for e in events if e["type"] == "TextDelta"]
    assert len(text_deltas) == 1
    assert text_deltas[0]["delta"] == "Hello world"


@pytest.mark.asyncio
async def test_stream_executor_run_finished_guaranteed_on_api_error():
    """RunFinished is always emitted by stream_executor, even when Anthropic API raises."""
    from unittest.mock import AsyncMock, MagicMock

    from src.agent.agui_stream import stream_executor

    mock_tool = MagicMock()
    mock_tool.name = "noop"
    mock_tool.description = ""
    mock_tool.inputSchema = {}

    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(return_value=[mock_tool])

    # Anthropic streaming context raises on entry (simulates API failure after RunStarted)
    failing_ctx = MagicMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("API down"))
    failing_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = failing_ctx

    with patch("src.agent.agui_stream.build_mcp_server", return_value=mock_mcp):
        events = []
        try:
            async for event in stream_executor("test", MagicMock(), anthropic_client=mock_client):
                events.append(json.loads(event["data"]))
        except Exception:
            pass  # exception re-raised after finally yields RunFinished

    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
