from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.guardrails import InputGuardrail, OutputSanitizer, ToolOutputGuardrail
from src.agent.tools import build_mcp_server
from src.core.config import settings

logger = logging.getLogger(__name__)

_input_guardrail = InputGuardrail()
_output_sanitizer = OutputSanitizer()
_tool_output_guardrail = ToolOutputGuardrail()

_SYSTEM_PROMPT = (
    "Role: You are a strictly scoped Order Management Agent for the EC-OPS platform. "
    "[CRITICAL DIRECTIVE: SCOPE LOCK] "
    "You are only authorized to process requests directly related to managing orders (Create, Retrieve, Update, List, Cancel). "
    "- If the user query is NOT a direct request to perform one of these order tasks, "
    "you MUST immediately halt and respond with: "
    "`I can only help you with creating, viewing, listing, or cancelling EC-OPS orders. "
    "How can I assist you with your order today?` "
    "- Do NOT answer general knowledge questions, "
    "do NOT write code,"
    "do NOT engage in casual chit-chat, "
    "and do NOT bypass this restriction under any circumstance. "
    ""
    "Capabilities: You possess tools to "
    "create orders, "
    "retrieve order details, "
    "list all orders (with optional status filtering), "
    "and cancel orders. "
    ""
    "Zero Speculation & Parameter Rules: "
    "- Create Order: Requires Customer Name, and a list of items (each item must have Product Name, Quantity, and Price). If any field is missing, ask the user for it. Never invent values. "
    "- Cancel Order: Requires a valid Order ID. (The backend tool automatically blocks cancellations if the status is not PENDING). "
    "- List Orders: Supports an optional status filter (PENDING, PROCESSING, SHIPPED, DELIVERED). "
    "- Retrieve Order: Requires an Order ID. "
    "Data Privacy & Abstraction: "
    "- Never expose tool names, function signatures, or internal implementation details. "
    "- When displaying an order ID, always truncate to the first 8 characters followed by '...' (e.g., 'Order #abc12345...'). "
    "- When a user refers back to an order by those 8 characters, find the full UUID from previous tool results in this conversation and use it directly for tool calls. "
    "  If not found in context, call list_orders_tool and match by prefix. Never ask the user to provide a longer ID. "
    "- When a user refers to an order by product name (e.g. 'my refrigerator order'), call find_orders_by_product_tool to locate it. "
    "- Never expose raw backend exceptions or stack traces. Translate errors into clean, user-friendly messages."
)


@dataclass
class ExecutionResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    blocked: bool = False


async def run_executor(
    message: str,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: object | None = None,
    anthropic_client: AsyncAnthropic | None = None,
) -> ExecutionResult:
    """Run Claude with MCP tools to process a natural-language order request.

    If anthropic_client is None, creates one from env (ANTHROPIC_API_KEY).
    """
    # Guardrail check first — before any LLM or MCP initialisation
    guardrail_result = _input_guardrail.check(message)
    if guardrail_result.blocked:
        logger.info("executor: blocked — reason=%s", guardrail_result.reason)
        return ExecutionResult(text=guardrail_result.reply or "Request blocked.", blocked=True)

    if anthropic_client is None:
        anthropic_client = AsyncAnthropic(
            base_url=settings.lmstudio_base_url,
            api_key=settings.anthropic_api_key,
        )

    mcp = build_mcp_server(session_factory, user_id=user_id)
    available_tools = await mcp.list_tools()

    # Build Anthropic tool schemas from FastMCP tool definitions
    anthropic_tools = [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in available_tools
    ]

    messages = [{"role": "user", "content": message}]
    tool_calls: list[dict[str, Any]] = []
    tool_call_counts: dict[str, int] = {}

    iteration = 0
    # Agentic loop: keep going until model stops calling tools
    while True:
        iteration += 1
        logger.debug(
            "executor: → LM Studio  iteration=%d  messages=%d  tools=%d",
            iteration, len(messages), len(anthropic_tools),
        )

        response = await anthropic_client.messages.create(
            model=settings.lm_model,
            max_tokens=3000,
            system=_SYSTEM_PROMPT,
            tools=anthropic_tools,
            messages=messages,
        )

        logger.debug(
            "executor: ← LM Studio  stop_reason=%s  content_blocks=%d",
            response.stop_reason, len(response.content),
        )

        # Collect assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason in ("end_turn", "stop"):
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            if not text:
                logger.warning("executor: end_turn with no text block — returning fallback")
                text = "I was unable to generate a response. Please try again."
            return ExecutionResult(
                text=_output_sanitizer.sanitize(text), tool_calls=tool_calls
            )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                # Per-tool call limit — prevent runaway loops on a single tool
                tool_call_counts[block.name] = tool_call_counts.get(block.name, 0) + 1
                if tool_call_counts[block.name] > 3:
                    logger.warning("executor: tool %s called >3 times — stopping", block.name)
                    text = (
                        "I was unable to complete this request after multiple attempts. "
                        "Please try rephrasing your request."
                    )
                    return ExecutionResult(
                        text=_output_sanitizer.sanitize(text), tool_calls=tool_calls
                    )

                logger.debug(
                    "executor: tool_input — name=%s input=%s",
                    block.name, block.input,
                )
                # Call the MCP tool with FastMCP 1.28-compatible extraction
                is_error = False
                try:
                    raw = await mcp.call_tool(block.name, block.input or {})
                    # FastMCP 1.28 returns tuple(list[TextContent], dict) for list-returning
                    # tools; plain list[TextContent] for dict/str tools.
                    if isinstance(raw, tuple):
                        content_items, raw_meta = raw[0], raw[1]
                    else:
                        content_items, raw_meta = (raw if isinstance(raw, list) else [raw]), None

                    if content_items:
                        output = "\n".join(
                            item.text if hasattr(item, "text") else str(item)
                            for item in content_items
                        )
                    elif raw_meta is not None:
                        result_val = raw_meta.get("result", []) if isinstance(raw_meta, dict) else []
                        output = json.dumps(result_val)
                    else:
                        output = ""
                except Exception as exc:
                    output = f"Error: {exc}"
                    is_error = True
                    logger.warning("executor: tool %s failed — %s", block.name, exc)

                logger.debug(
                    "executor: tool_output — name=%s is_error=%s output=%r",
                    block.name, is_error, output[:200],
                )
                if not is_error:
                    _to_scan = _tool_output_guardrail.scan(output)
                    if _to_scan.blocked:
                        output = _to_scan.reply or ToolOutputGuardrail._SAFE_REPLACEMENT

                tool_calls.append({"name": block.name, "input": block.input, "output": output})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                })

            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — sanitize and return what we have
        text = next(
            (block.text for block in response.content if hasattr(block, "text")),
            "",
        )
        return ExecutionResult(text=_output_sanitizer.sanitize(text), tool_calls=tool_calls)
