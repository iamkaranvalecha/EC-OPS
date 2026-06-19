from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.agent.a2a_router import router as a2a_router
from src.core.database import async_session
from src.orders.router import router as orders_router
from src.scheduler.setup import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler(async_session)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="EC-OPS", version="0.1.0", lifespan=lifespan)
app.include_router(orders_router)
app.include_router(a2a_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
