from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.agent.executor import ExecutionResult, run_executor
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.core.config import settings as _settings
from src.core.database import async_session as _prod_session_factory

router = APIRouter(tags=["a2a"])
logger = logging.getLogger(__name__)

# ── In-memory task store (keyed by task id) ──────────────────────────────────
# Each entry: {id, status: pending|completed|failed, result: dict|None, error: str|None}
_tasks: dict[str, dict[str, Any]] = {}
# Held so the event loop doesn't garbage-collect in-flight coroutines on SIGTERM/reload
_task_handles: dict[str, asyncio.Task] = {}


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
async def agent_card(_: User = Depends(get_current_user)) -> dict:
    return AGENT_CARD


# ── Task endpoints ─────────────────────────────────────────────────────────────

async def _run_task(task_id: str, message: str, user_id: uuid.UUID | None = None) -> None:
    logger.info("a2a: task %s started — message=%r user=%s", task_id, message[:120], user_id)
    try:
        exec_result: ExecutionResult = await run_executor(message, _prod_session_factory, user_id=user_id)
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["result"] = {
            "text": exec_result.text,
            "tool_calls": exec_result.tool_calls,
        }
        logger.info("a2a: task %s completed — tool_calls=%d", task_id, len(exec_result.tool_calls))
    except Exception as exc:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(exc)
        logger.error("a2a: task %s failed — %s", task_id, exc)
    finally:
        _task_handles.pop(task_id, None)


@router.post("/a2a/tasks/send", response_model=TaskResponse, status_code=202)
async def send_task(
    body: TaskSendRequest, current_user: User = Depends(get_current_user)
) -> TaskResponse:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"id": task_id, "status": "pending", "result": None, "error": None}
    _task_handles[task_id] = asyncio.create_task(
        _run_task(task_id, body.message, user_id=current_user.id)
    )
    logger.info("a2a: task %s accepted — message=%r", task_id, body.message[:120])
    return TaskResponse(**_tasks[task_id])


@router.get("/a2a/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, _: User = Depends(get_current_user)) -> TaskResponse:
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return TaskResponse(**task)
