# Implementation Plan — patch-status

Stack: Python 3.12 + FastAPI + SQLAlchemy async | Existing order domain in src/orders/ | MCP tools in src/agent/tools.py

## Phase 1 — Domain layer
Milestone: patch-status-mvp
Goal: State machine dict, typed exception, and service function; no HTTP or MCP wiring yet.
Spec requirements covered: R1, R2, R3, R4
Tasks: T001, T002

## Phase 2 — REST + MCP layer
Milestone: patch-status-mvp
Goal: PATCH endpoint wired into the router; MCP tool registered on the server; guardrail allowlist updated.
Spec requirements covered: R5, R6, R7
Tasks: T003, T004

## Phase 3 — Test coverage
Milestone: patch-status-mvp
Goal: Exhaustive combination matrix, service/router unit tests, MCP tool tests, integration tests all green.
Spec requirements covered: R8
Tasks: T005

---

## Phase 1 — Domain layer

### T001 — OrderStatusUpdate schema + _VALID_TRANSITIONS + OrderStatusTransitionError
- Spec req: R1, R2, R3 · Signals: S2, S5
- Scope: src/orders/schemas.py, src/orders/service.py, src/orders/exceptions.py
- Done when: `OrderStatusUpdate(status: OrderStatus)` added to schemas; `_VALID_TRANSITIONS` dict
  maps each of the 5 statuses to its valid next states (empty set for terminals); `OrderStatusTransitionError`
  added to exceptions.py (truncates order_id to 8 chars in __init__).

### T002 — update_order_status() service function
- Spec req: R4 · Signals: S1, S2, S3, S4
- Scope: src/orders/service.py
- Done when: `async def update_order_status(order_id, new_status, session, user_id=None) → Order`;
  delegates to `get_order()` for not-found/user-scope check; validates transition; sets status +
  updated_at; commits; refreshes and returns order.

## Phase 2 — REST + MCP layer

### T003 — PATCH /orders/{id}/status endpoint
- Spec req: R5 · Signals: S1, S2, S3, S4
- Scope: src/orders/router.py
- Done when: `@router.patch("/{order_id}/status", response_model=OrderResponse)` route added;
  maps `OrderNotFound` → 404, `OrderStatusTransitionError` → 422; requires `get_current_user` dep.

### T004 — update_order_status_tool + guardrail update
- Spec req: R6, R7 · Signals: S6, S7, S8, S9
- Scope: src/agent/tools.py, src/agent/guardrails.py
- Done when: `update_order_status_tool(order_id: str, status: str) → dict` registered as @mcp.tool();
  UUID and status validated before DB call; all exceptions re-raised as ValueError; docstring describes
  valid transitions; `"update_order_status_tool"` added to `_TOOL_NAMES` frozenset.

## Phase 3 — Test coverage

### T005 — Full test suite: service + router + combinations + MCP + integration
- Spec req: R8 · Signals: S1–S9
- Scope: tests/orders/test_service.py, tests/orders/test_router.py, tests/orders/test_combinations.py,
  tests/agent/test_mcp_server.py, tests/integration/test_orders_api.py
- Done when: 7 service tests (3 valid transitions + 4 error cases); 4 router tests (200/422/422/404);
  exhaustive 5×5 matrix in test_combinations.py (all 25 combinations); 5 MCP tool tests (error paths +
  valid dict return); 8 integration tests (lifecycle via PATCH + all error codes); `uv run pytest` green.
