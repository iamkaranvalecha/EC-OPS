from __future__ import annotations

import asyncio

from src.agent.tools import build_mcp_server
from src.core.database import async_session

mcp = build_mcp_server(async_session)

if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
