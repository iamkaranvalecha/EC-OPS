from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette.sse import EventSourceResponse

from src.agent.events import (
    RunFinished,
    RunStarted,
    TextDelta,
    ToolCallResult,
    ToolCallStart,
    UiAction,
)
from src.agent.tools import build_mcp_server
from src.core.config import settings as _settings
from src.core.database import async_session as _prod_session_factory

router = APIRouter(tags=["agui"])

_MAX_ITERATIONS = 10
_ORDER_CARD_TOOLS = frozenset({"create_order_tool", "get_order_tool"})


class _ReasoningFilter:
    """Strip <think>…</think> reasoning blocks from streaming text.

    Handles tag boundaries split across chunks so no reasoning leaks
    regardless of how the model streams its output.
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._in_think = False
        self._tail = ""  # chars held back while a partial open-tag is possible

    def feed(self, chunk: str) -> str:
        """Feed one streamed chunk; return clean text to emit (may be empty)."""
        self._tail += chunk
        out: list[str] = []

        while self._tail:
            if self._in_think:
                idx = self._tail.find(self._CLOSE)
                if idx == -1:
                    self._tail = ""
                    break
                self._tail = self._tail[idx + len(self._CLOSE):]
                self._in_think = False
            else:
                idx = self._tail.find(self._OPEN)
                if idx == -1:
                    # No open tag visible — but the tail might end with a partial "<think"
                    hold = 0
                    for n in range(1, len(self._OPEN)):
                        if self._OPEN.startswith(self._tail[-n:]):
                            hold = n
                            break
                    emit_to = len(self._tail) - hold
                    out.append(self._tail[:emit_to])
                    self._tail = self._tail[emit_to:]
                    break
                out.append(self._tail[:idx])
                self._tail = self._tail[idx + len(self._OPEN):]
                self._in_think = True

        return "".join(out)


async def stream_executor(
    message: str,
    session_factory: async_sessionmaker[AsyncSession],
    anthropic_client: AsyncAnthropic | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield AG-UI SSE event dicts for each step of the agent run.

    Event order: RunStarted -> TextDelta* -> (ToolCallStart, ToolCallResult)* -> RunFinished
    RunFinished is always emitted, even if an exception occurs mid-stream.
    Reasoning tokens (<think>…</think>) are stripped before any TextDelta is emitted.
    """
    if anthropic_client is None:
        anthropic_client = AsyncAnthropic(
            base_url=_settings.lmstudio_base_url,
            api_key=_settings.anthropic_api_key,
        )

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
            _filter = _ReasoningFilter()

            async with anthropic_client.messages.stream(
                model=_settings.lm_model,
                max_tokens=3000,
                tools=anthropic_tools,
                messages=messages,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    clean = _filter.feed(text_chunk)
                    if clean:
                        current_text += clean
                        yield {"data": TextDelta(delta=clean).to_sse()}

                response = await stream.get_final_message()

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason in ("end_turn", "stop"):
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

                    if block.name in _ORDER_CARD_TOOLS:
                        try:
                            parsed = json.loads(output)
                            if isinstance(parsed, dict) and "id" in parsed:
                                yield {"data": UiAction(payload=parsed).to_sse()}
                        except (json.JSONDecodeError, TypeError):
                            pass

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
