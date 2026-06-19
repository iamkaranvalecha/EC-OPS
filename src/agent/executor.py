from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.tools import build_mcp_server


@dataclass
class ExecutionResult:
    text: str                          # Claude's final text response
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # each: {name, input, output}


async def run_executor(
    message: str,
    session_factory: async_sessionmaker[AsyncSession],
    anthropic_client: AsyncAnthropic | None = None,
) -> ExecutionResult:
    """Run Claude with MCP tools to process a natural-language order request.

    If anthropic_client is None, creates one from env (ANTHROPIC_API_KEY).
    """
    if anthropic_client is None:
        anthropic_client = AsyncAnthropic()

    mcp = build_mcp_server(session_factory)
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

    # Agentic loop: keep going until Claude stops calling tools
    while True:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=anthropic_tools,
            messages=messages,
        )

        # Collect assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract final text
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            return ExecutionResult(text=text, tool_calls=tool_calls)

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                # Call the MCP tool
                content = await mcp.call_tool(block.name, block.input or {})
                output = content[0].text if content else ""
                tool_calls.append({"name": block.name, "input": block.input, "output": output})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — return what we have
        text = next(
            (block.text for block in response.content if hasattr(block, "text")),
            "",
        )
        return ExecutionResult(text=text, tool_calls=tool_calls)
