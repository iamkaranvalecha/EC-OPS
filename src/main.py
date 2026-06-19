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


app = FastAPI(title="EC-OPS", version="0.1.0", lifespan=lifespan)
app.include_router(orders_router)
app.include_router(a2a_router)
app.include_router(agui_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Mount static frontend LAST so API routes always take precedence
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    from src.core.config import settings

    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=True)
