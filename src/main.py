from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.agent.a2a_router import router as a2a_router
from src.agent.agui_stream import router as agui_router
from src.core.database import async_session
from src.orders.router import router as orders_router
from src.scheduler.setup import create_scheduler

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler(async_session)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="EC-OPS",
    version="0.1.0",
    description=(
        "E-Commerce Order Processing System — REST API for order lifecycle management "
        "with a background status promotion scheduler, MCP tools, A2A protocol, and an "
        "AI agent via AG-UI SSE streaming (powered by local LM Studio).\n\n"
        "**Order lifecycle:** `PENDING` → `PROCESSING` (auto, every 5 min) "
        "→ `SHIPPED` → `DELIVERED`\n\n"
        "**Validation:** `POST /orders` returns 422 for empty names, empty items list, "
        "zero/negative quantity, or negative price."
    ),
    openapi_tags=[
        {
            "name": "orders",
            "description": "Create, retrieve, list, and cancel orders. "
            "Only `PENDING` orders can be cancelled — all others return 409.",
        },
        {
            "name": "agent",
            "description": "AG-UI SSE stream — send a natural-language message and receive "
            "a real-time stream of `RunStarted`, `TextDelta`, `ToolCallStart`, "
            "`ToolCallResult`, `UiAction`, and `RunFinished` events.",
        },
        {
            "name": "a2a",
            "description": "Agent-to-Agent protocol — fire-and-forget task submission "
            "(202 Accepted) with status polling. Agent Card at `/.well-known/agent.json`.",
        },
        {
            "name": "system",
            "description": "Health check.",
        },
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.include_router(orders_router)
app.include_router(a2a_router)
app.include_router(agui_router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


# Mount static frontend LAST so API routes always take precedence
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    from src.core.config import settings

    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=True)
