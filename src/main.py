from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orders.router import router as orders_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="EC-OPS", version="0.1.0", lifespan=lifespan)

app.include_router(orders_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
