from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette.sse import EventSourceResponse

from src.agent.events import RunFinished, RunStarted, TextDelta, ToolCallResult, ToolCallStart
from src.agent.tools import build_mcp_server
from src.core.database import async_session as _prod_session_factory

router = APIRouter(tags=["agui"])

_MAX_ITERATIONS = 10


async def stream_executor(
    message: str,
    session_factory: async_sessionmaker[AsyncSession],
    anthropic_client: AsyncAnthropic | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield AG-UI SSE event dicts for each step of the agent run.

    Event order: RunStarted -> TextDelta* -> (ToolCallStart, ToolCallResult)* -> RunFinished
    RunFinished is always emitted, even if an exception occurs mid-stream.
    """
    if anthropic_client is None:
        anthropic_client = AsyncAnthropic()

    mcp = build_mcp_server(session_factory)
    available_tools = await mcp.list_tools()
    anthropic_tools = [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in available_tools
    ]

    yield {"data": RunStarted().to_sse()}

    messages: list[dict] = [{"role": "user", "content": message}]

    try:
        for _ in range(_MAX_ITERATIONS):
            current_text = ""

            async with anthropic_client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                tools=anthropic_tools,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if type(event).__name__ == "RawContentBlockDeltaEvent":
                        delta = event.delta
                        if hasattr(delta, "text") and delta.text:
                            current_text += delta.text
                            yield {"data": TextDelta(delta=delta.text).to_sse()}

                response = await stream.get_final_message()

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tc_id = block.id
                    yield {"data": ToolCallStart(tool_name=block.name, tool_call_id=tc_id).to_sse()}

                    raw = await mcp.call_tool(block.name, block.input or {})
                    if not raw:
                        output = ""
                    elif hasattr(raw[0], "text"):
                        output = raw[0].text
                    else:
                        output = str(raw[0])

                    yield {"data": ToolCallResult(tool_call_id=tc_id, result=output).to_sse()}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc_id,
                        "content": output,
                    })

                if not tool_results:
                    break
                messages.append({"role": "user", "content": tool_results})
                continue

            break
    finally:
        yield {"data": RunFinished().to_sse()}


@router.get("/agent/stream")
async def agent_stream(
    message: str = Query(default="List all orders", max_length=2000),
) -> EventSourceResponse:
    async def event_generator():
        async for event in stream_executor(message, _prod_session_factory):
            yield event

    return EventSourceResponse(event_generator())
