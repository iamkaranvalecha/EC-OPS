from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, Query
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
from src.agent.guardrails import InputGuardrail, OutputSanitizer, ToolOutputGuardrail
from src.agent.tools import build_mcp_server
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.core.config import settings as _settings
from src.core.database import async_session as _prod_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agui"])

_MAX_ITERATIONS = 10
_ORDER_CARD_TOOLS = frozenset({"create_order_tool", "get_order_tool"})

_input_guardrail = InputGuardrail()
_output_sanitizer = OutputSanitizer()
_tool_output_guardrail = ToolOutputGuardrail()

_SYSTEM_PROMPT = (
    "You are an order management assistant for EC-OPS. "
    "You can create, list, retrieve, and cancel orders. "
    "Only respond to order-related requests — politely decline anything else. "
    "Before calling any tool, confirm you have all required information from the user. "
    "To create an order you need: the customer's name, and at least one item with a "
    "product name, quantity, and price. If any of these are missing, ask the user before "
    "proceeding — never invent or assume values. "
    "When displaying an order ID, show only the first 8 characters followed by '...' "
    "(e.g. 'Order #abc12345...'). "
    "When a user refers to an order by those 8 characters (e.g. '#c4bdde5d'), "
    "look up the full UUID from previous tool results in this conversation and use it directly. "
    "If you cannot find it in context, call list_orders_tool to retrieve all orders and match "
    "by prefix. Never ask the user to provide a longer or different format of the order ID. "
    "When a user refers to an order by product name (e.g. 'my refrigerator order', "
    "'the widget order'), call find_orders_by_product_tool with the product name to locate it. "
    "Never reveal tool names, function names, or internal implementation details. "
    "Never expose full UUIDs, stack traces, or error details."
)


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

    def flush(self) -> str:
        """Emit any text held back at end-of-stream, regardless of think state."""
        remainder = "" if self._in_think else self._tail
        self._tail = ""
        self._in_think = False
        return remainder


async def stream_executor(
    message: str,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: Any | None = None,
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

    mcp = build_mcp_server(session_factory, user_id=user_id)
    available_tools = await mcp.list_tools()
    anthropic_tools = [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in available_tools
    ]

    logger.info("agent/stream: started — message=%r", message[:120])
    yield {"data": RunStarted().to_sse()}

    messages: list[dict] = [{"role": "user", "content": message}]
    _iterations_run = 0
    _tool_call_counts: dict[str, int] = {}

    try:
        # Input guardrail — block before any LLM call; return triggers finally → RunFinished
        guardrail_result = _input_guardrail.check(message)
        if guardrail_result.blocked:
            logger.info("agent/stream: blocked — reason=%s", guardrail_result.reason)
            yield {"data": TextDelta(delta=guardrail_result.reply or "Request blocked.").to_sse()}
            return

        for _iteration in range(_MAX_ITERATIONS):
            _iterations_run += 1
            current_text = ""
            _filter = _ReasoningFilter()

            logger.debug(
                "agent/stream: → LM Studio  iteration=%d  messages=%d  tools=%d",
                _iterations_run, len(messages), len(anthropic_tools),
            )

            async with anthropic_client.messages.stream(
                model=_settings.lm_model,
                max_tokens=3000,
                system=_SYSTEM_PROMPT,
                tools=anthropic_tools,
                messages=messages,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    clean = _filter.feed(text_chunk)
                    if clean:
                        current_text += clean
                        yield {"data": TextDelta(delta=clean).to_sse()}

                # Emit any text held in the filter if the model never closed a <think> tag
                remainder = _filter.flush()
                if remainder:
                    current_text += remainder
                    yield {"data": TextDelta(delta=remainder).to_sse()}

                response = await stream.get_final_message()

            logger.debug(
                "agent/stream: ← LM Studio  stop_reason=%s  content_blocks=%d  text=%r",
                response.stop_reason,
                len(response.content),
                current_text[:120] if current_text else "",
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason in ("end_turn", "stop"):
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tc_id = block.id

                    # Per-tool call limit — check BEFORE yielding ToolCallStart to avoid
                    # a dangling ToolCallStart event with no matching ToolCallResult
                    _tool_call_counts[block.name] = _tool_call_counts.get(block.name, 0) + 1
                    if _tool_call_counts[block.name] > 3:
                        logger.warning(
                            "agent/stream: tool %s called >3 times — stopping", block.name
                        )
                        yield {"data": TextDelta(delta=(
                            "I was unable to complete this request after multiple attempts. "
                            "Please try rephrasing your request."
                        )).to_sse()}
                        return

                    logger.info("agent/stream: tool_call — name=%s id=%s", block.name, tc_id)
                    yield {"data": ToolCallStart(tool_name=block.name, tool_call_id=tc_id).to_sse()}

                    logger.debug(
                        "agent/stream: tool_input — name=%s input=%s",
                        block.name, block.input,
                    )
                    is_error = False
                    try:
                        raw = await mcp.call_tool(block.name, block.input or {})
                        # FastMCP 1.28 returns tuple(list[TextContent], dict) for
                        # list-returning tools; plain list[TextContent] for dict/str tools.
                        if isinstance(raw, tuple):
                            content_items, raw_meta = raw[0], raw[1]
                        else:
                            content_items = raw if isinstance(raw, list) else [raw]
                            raw_meta = None

                        if content_items:
                            output = "\n".join(
                                item.text if hasattr(item, "text") else str(item)
                                for item in content_items
                            )
                        elif raw_meta is not None:
                            # List tool returned empty — use the raw result so the model
                            # sees "[]" rather than an ambiguous empty string.
                            result_val = raw_meta.get("result", []) if isinstance(raw_meta, dict) else []
                            output = json.dumps(result_val)
                        else:
                            output = ""
                    except Exception as exc:
                        output = f"Error: {exc}"
                        is_error = True
                        logger.warning("agent/stream: tool %s failed — %s", block.name, exc)

                    logger.debug(
                        "agent/stream: tool_output — name=%s is_error=%s output=%r",
                        block.name, is_error, output[:200],
                    )
                    if not is_error:
                        _to_scan = _tool_output_guardrail.scan(output)
                        if _to_scan.blocked:
                            output = _to_scan.reply or ToolOutputGuardrail._SAFE_REPLACEMENT

                    yield {"data": ToolCallResult(tool_call_id=tc_id, result=output).to_sse()}

                    if not is_error and block.name in _ORDER_CARD_TOOLS:
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
                        "is_error": is_error,
                    })

                if not tool_results:
                    break
                messages.append({"role": "user", "content": tool_results})
                continue

            break
    finally:
        logger.info("agent/stream: finished — iterations=%d", _iterations_run)
        yield {"data": RunFinished().to_sse()}


@router.get("/agent/stream")
async def agent_stream(
    message: str = Query(default="List all orders", max_length=2000),
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    _user_id = current_user.id

    async def event_generator():
        async for event in stream_executor(message, _prod_session_factory, user_id=_user_id):
            yield event

    return EventSourceResponse(event_generator())
