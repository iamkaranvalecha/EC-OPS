from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agent.executor import ExecutionResult, run_executor
from src.core.config import settings as _settings
from src.core.database import async_session as _prod_session_factory

router = APIRouter(tags=["a2a"])

# ── In-memory task store (keyed by task id) ──────────────────────────────────
# Each entry: {id, status: pending|completed|failed, result: dict|None, error: str|None}
_tasks: dict[str, dict[str, Any]] = {}


class TaskSendRequest(BaseModel):
    message: str


class TaskResponse(BaseModel):
    id: str
    status: str
    result: dict | None = None
    error: str | None = None


# ── Agent Card ────────────────────────────────────────────────────────────────

AGENT_CARD = {
    "name": "EC-OPS Order Agent",
    "description": "Processes natural-language order requests: create, retrieve, list, cancel.",
    "version": "0.1.0",
    "url": f"http://localhost:{_settings.port}",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "create_order",
            "name": "Create Order",
            "description": "Place a new order with items.",
            "tags": ["orders"],
            "examples": ["Create an order for Alice with 2 widgets at $5 each"],
        },
        {
            "id": "get_order",
            "name": "Get Order",
            "description": "Retrieve order details by ID.",
            "tags": ["orders"],
            "examples": ["Get order abc123"],
        },
        {
            "id": "list_orders",
            "name": "List Orders",
            "description": "List all orders, optionally filtered by status.",
            "tags": ["orders"],
            "examples": ["List all pending orders"],
        },
        {
            "id": "cancel_order",
            "name": "Cancel Order",
            "description": "Cancel a PENDING order by ID.",
            "tags": ["orders"],
            "examples": ["Cancel order abc123"],
        },
    ],
}


@router.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return AGENT_CARD


# ── Task endpoints ─────────────────────────────────────────────────────────────

async def _run_task(task_id: str, message: str) -> None:
    try:
        exec_result: ExecutionResult = await run_executor(message, _prod_session_factory)
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["result"] = {
            "text": exec_result.text,
            "tool_calls": exec_result.tool_calls,
        }
    except Exception as exc:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(exc)


@router.post("/a2a/tasks/send", response_model=TaskResponse, status_code=202)
async def send_task(body: TaskSendRequest) -> TaskResponse:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"id": task_id, "status": "pending", "result": None, "error": None}
    # Fire-and-forget: return 202 immediately; background task updates status
    asyncio.create_task(_run_task(task_id, body.message))
    return TaskResponse(**_tasks[task_id])


@router.get("/a2a/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return TaskResponse(**task)
