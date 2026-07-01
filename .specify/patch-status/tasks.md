# Tasks — patch-status

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — OrderStatusUpdate schema + _VALID_TRANSITIONS + OrderStatusTransitionError
- **Status**: [x]
- **Phase**: 1 — Domain layer
- **Milestone**: patch-status-mvp
- **Spec requirement**: R1, R2, R3
- **Goal signals**: S2, S5
- **Scope**: src/orders/schemas.py, src/orders/service.py, src/orders/exceptions.py
- **Done when**:
  - `OrderStatusUpdate(status: OrderStatus)` Pydantic model added to `src/orders/schemas.py`.
    An invalid status string (not an `OrderStatus` enum value) causes FastAPI to return 422.
  - `_VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]]` constant in `src/orders/service.py`:
    `PENDING → {PROCESSING}`, `PROCESSING → {SHIPPED}`, `SHIPPED → {DELIVERED}`,
    `DELIVERED → set()`, `CANCELLED → set()`.
  - `OrderStatusTransitionError(order_id, from_status, to_status)` in `src/orders/exceptions.py`;
    `short_id = str(order_id)[:8] + "..."` in constructor so no full UUID appears in error text.
  - `ruff check src/orders/` passes.
- **Brief**: Pure domain additions — no HTTP or MCP wiring in this task. The dict and exception
  are the foundation that T002–T004 build on.

## T002 — `update_order_status()` service function
- **Status**: [x]
- **Phase**: 1 — Domain layer
- **Milestone**: patch-status-mvp
- **Spec requirement**: R4
- **Goal signals**: S1, S2, S3
- **Scope**: src/orders/service.py
- **Done when**:
  - `async def update_order_status(order_id: UUID, new_status: OrderStatus, session: AsyncSession,
    user_id: UUID | None = None) → Order` is defined.
  - Calls `get_order(order_id, session, user_id=user_id)` — raises `OrderNotFound` if missing
    or if `user_id` doesn't match (enforces per-user scoping at the service level).
  - Captures `old_status = order.status` before mutation (avoids logging the already-updated value).
  - Raises `OrderStatusTransitionError(order_id, old_status.value, new_status.value)` when
    `new_status not in _VALID_TRANSITIONS[old_status]`.
  - Sets `order.status = new_status` and `order.updated_at = datetime.now(timezone.utc)`.
  - Commits, refreshes order (so items are loaded), and returns.
  - Service-layer unit tests (7):
    - `test_update_order_status_pending_to_processing` — 200, status updated
    - `test_update_order_status_processing_to_shipped` — 200
    - `test_update_order_status_shipped_to_delivered` — 200
    - `test_update_order_status_invalid_transition_raises` — OrderStatusTransitionError
    - `test_update_order_status_terminal_delivered_raises` — OrderStatusTransitionError
    - `test_update_order_status_terminal_cancelled_raises` — OrderStatusTransitionError
    - `test_update_order_status_not_found_raises` — OrderNotFound
- **Brief**: The service is protocol-agnostic. The same function is called by the REST router
  (T003) and the MCP tool (T004) — business logic lives once.

## T003 — `PATCH /orders/{order_id}/status` REST endpoint
- **Status**: [x]
- **Phase**: 2 — REST + MCP layer
- **Milestone**: patch-status-mvp
- **Spec requirement**: R5
- **Goal signals**: S1, S2, S3, S4
- **Scope**: src/orders/router.py
- **Done when**:
  - Route added (inserted before the DELETE handler to follow REST ordering conventions):
    ```python
    @router.patch("/{order_id}/status", response_model=OrderResponse)
    async def update_order_status_route(
        order_id: UUID, data: OrderStatusUpdate,
        session: AsyncSession = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) → OrderResponse
    ```
  - `OrderNotFound` → `HTTPException(404)`.
  - `OrderStatusTransitionError` → `HTTPException(422)`.
  - Invalid `status` value in body → 422 (FastAPI Pydantic validation, not caught in handler).
  - Invalid UUID in path → 422 (FastAPI path parameter validation).
  - No auth token → 401 (from `get_current_user` dependency).
  - Router tests (4):
    - `test_patch_order_status_returns_200` — valid transition, body has updated status
    - `test_patch_order_status_returns_422_on_invalid_transition` — DELIVERED→PENDING
    - `test_patch_order_status_returns_404_when_not_found` — unknown order ID
    - `test_patch_order_status_returns_422_on_invalid_status_value` — bad string in body
- **Brief**: Thin HTTP layer — no business logic, just maps domain exceptions to HTTP codes.

## T004 — `update_order_status_tool` + guardrail `_TOOL_NAMES` update
- **Status**: [x]
- **Phase**: 2 — REST + MCP layer
- **Milestone**: patch-status-mvp
- **Spec requirement**: R6, R7
- **Goal signals**: S6, S7, S8, S9
- **Scope**: src/agent/tools.py, src/agent/guardrails.py
- **Done when**:
  - Seventh `@mcp.tool()` in `build_mcp_server()`:
    ```python
    async def update_order_status_tool(order_id: str, status: str) → dict
    ```
  - UUID validation: `try: order_uuid = UUID(order_id) except ValueError: raise ValueError(...)`.
  - Status validation: `try: new_status = OrderStatus(status) except ValueError: raise ValueError(...)`.
    Error message includes `"Must be one of: PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED"`.
  - `OrderNotFound` and `OrderStatusTransitionError` both caught and re-raised as `ValueError`.
  - Returns dict: `{"id": ..., "customer_name": ..., "status": ..., "updated_at": ..., "items": [...]}`.
  - Docstring describes valid transitions and terminal states for the LLM's benefit.
  - `_TOOL_NAMES` frozenset in `src/agent/guardrails.py` updated to include
    `"update_order_status_tool"` (7 names total).
  - `ruff check src/agent/tools.py src/agent/guardrails.py` passes.

## T005 — Exhaustive test coverage (combinations + MCP + integration)
- **Status**: [x]
- **Phase**: 3 — Test coverage
- **Milestone**: patch-status-mvp
- **Spec requirement**: R8
- **Goal signals**: S1–S9
- **Scope**: tests/orders/test_combinations.py, tests/agent/test_mcp_server.py,
  tests/integration/test_orders_api.py
- **Done when**:
  - `tests/orders/test_combinations.py` — exhaustive parametrized tests:
    - All 3 valid transitions (no exception raised)
    - All 22 invalid transitions (OrderStatusTransitionError raised) across the full 5×5 matrix
    - All 5 status values for `list_orders` status filter
    - All 4 non-PENDING cancel combinations (OrderNotCancellable raised at service and router)
    - Create variants (single item, 3 items, zero price, large quantity)
    - Scheduler config assertions (5-min interval, max_instances=1, coalesce=True, job ID)
  - `tests/agent/test_mcp_server.py` updated:
    - `EXPECTED_TOOLS` set contains 7 tool names (including `update_order_status_tool`)
    - 5 new tool tests: invalid UUID, invalid status, not found, invalid transition, valid return dict
  - `tests/integration/test_orders_api.py` — 8 new PATCH integration tests:
    - Full PENDING→PROCESSING→SHIPPED→DELIVERED via PATCH
    - Terminal DELIVERED blocks further PATCH (422)
    - Terminal CANCELLED blocks PATCH (422)
    - Skipping a step returns 422
    - Nonexistent order returns 404
    - Invalid UUID in path returns 422
    - Bad status string in body returns 422
    - Cross-user protection: user B cannot PATCH user A's order → 404
  - `uv run pytest tests/orders/test_combinations.py tests/agent/test_mcp_server.py tests/integration/test_orders_api.py` fully passes.
