import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.agent.a2a_router import router as a2a_router
from src.agent.agui_stream import router as agui_router
from src.auth.router import router as auth_router
from src.core.database import async_session
from src.orders.router import router as orders_router
from src.scheduler.setup import create_scheduler

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

from src.core.config import settings as _boot_settings

_LOG_LEVEL = getattr(logging, _boot_settings.log_level.upper(), logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
# Keep noisy libraries at WARNING unless the user explicitly wants DEBUG
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
# httpx carries the raw HTTP traffic to LM Studio — surface it at DEBUG
if _LOG_LEVEL <= logging.DEBUG:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.DEBUG)
else:
    logging.getLogger("httpx").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EC-OPS starting up — scheduler starting")
    scheduler = create_scheduler(async_session)
    scheduler.start()
    yield
    logger.info("EC-OPS shutting down — scheduler stopping")
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
            "name": "auth",
            "description": "Register and obtain JWT Bearer tokens. "
            "Pass the token as `Authorization: Bearer <token>` on all other requests.",
        },
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
app.include_router(auth_router)
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

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        reload_dirs=["src"],
    )
