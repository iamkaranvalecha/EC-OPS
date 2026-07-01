# Spec — patch-status

## Verbatim request

> verify everything exists.. all possible combination testing should be done too
> [order update status requirement: "Update order status: The order should have statuses like PENDING,
> PROCESSING, SHIPPED, and DELIVERED. A background job should automatically update PENDING orders to
> PROCESSING every 5 minutes."]

> verify again in depth. these changes will work when requests are coming from ai agent right?
> i want feature parity across stack

## Background

The original `order-processing` spec covered the background scheduler (PENDING → PROCESSING) but did
not expose a REST endpoint for advancing orders through the remaining states (PROCESSING → SHIPPED →
DELIVERED). A gap audit found:
- No `PATCH /orders/{id}/status` endpoint existed — only the scheduler could change order status.
- No MCP tool for status transitions — the AI agent had no way to advance orders beyond PROCESSING.
- No exhaustive test coverage for valid/invalid transition combinations.

This feature adds the missing endpoint, the MCP tool, and full-stack test coverage to achieve
feature parity between the REST API, the AI agent layer, and the background scheduler.

## Requirements

### R1 — `OrderStatusUpdate` schema
- R1.1 — A `OrderStatusUpdate` Pydantic model in `src/orders/schemas.py` with a single
  field: `status: OrderStatus`.
- R1.2 — An invalid status string returns 422 (Pydantic enum coercion).

### R2 — State machine (`_VALID_TRANSITIONS`)
- R2.1 — A `_VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]]` constant in
  `src/orders/service.py` encodes every permitted status change:
  ```
  PENDING     → {PROCESSING}
  PROCESSING  → {SHIPPED}
  SHIPPED     → {DELIVERED}
  DELIVERED   → {}   (terminal)
  CANCELLED   → {}   (terminal)
  ```
- R2.2 — The dict is the single source of truth — no parallel `if/elif` chains elsewhere.
- R2.3 — All 25 combinations of (current_status × target_status) must have deterministic,
  tested behaviour: 3 valid transitions and 22 invalid ones.

### R3 — `OrderStatusTransitionError` exception
- R3.1 — `OrderStatusTransitionError(order_id, from_status, to_status)` added to
  `src/orders/exceptions.py`. Constructor truncates `order_id` to 8 chars (`short_id + "..."`)
  so full UUIDs never appear in error messages.
- R3.2 — Raised by `update_order_status()` when the target status is not in
  `_VALID_TRANSITIONS[current_status]`.

### R4 — `update_order_status()` service function
- R4.1 — Async function in `src/orders/service.py`:
  `update_order_status(order_id, new_status, session, user_id=None) → Order`
- R4.2 — Calls `get_order()` first (raising `OrderNotFound` if absent or belongs to another user).
- R4.3 — Validates transition against `_VALID_TRANSITIONS`; raises `OrderStatusTransitionError`
  on violation.
- R4.4 — Sets `order.status = new_status` and `order.updated_at = datetime.now(timezone.utc)`.
- R4.5 — Returns the refreshed order (with items loaded via selectin).

### R5 — `PATCH /orders/{id}/status` REST endpoint
- R5.1 — Route: `PATCH /orders/{order_id}/status`, body: `OrderStatusUpdate`, response: `OrderResponse`.
- R5.2 — 200 on success, with the updated order in the response body.
- R5.3 — 422 if the transition is invalid (status body schema violation OR state-machine violation).
- R5.4 — 404 if the order ID does not exist or belongs to another user.
- R5.5 — 422 if the status string is not a recognized `OrderStatus` value.
- R5.6 — 401 without a valid Bearer token (auth dependency from the auth feature).

### R6 — `update_order_status_tool` MCP tool
- R6.1 — Registered on the MCP server in `src/agent/tools.py` alongside the existing 6 tools.
- R6.2 — Signature: `update_order_status_tool(order_id: str, status: str) → dict`.
- R6.3 — Validates the UUID string before any DB call; raises `ValueError` with a readable
  message on an invalid UUID.
- R6.4 — Validates the status string against `OrderStatus` enum; raises `ValueError` with a
  `"Must be one of: ..."` message on an invalid value.
- R6.5 — Catches `OrderNotFound` and `OrderStatusTransitionError` and re-raises as `ValueError`
  so the LLM receives a human-readable error message, not a raw Python exception.
- R6.6 — Returns a dict with keys: `id`, `customer_name`, `status`, `updated_at`, `items`.
- R6.7 — Docstring describes valid transitions and terminal states for the LLM's benefit.

### R7 — Guardrail tool allowlist update
- R7.1 — `_TOOL_NAMES` frozenset in `src/agent/guardrails.py` includes `"update_order_status_tool"`.
- R7.2 — Omitting it from the frozenset would cause the guardrail to block or mishandle agent calls
  to the new tool; including it ensures the tool name is recognized.

### R8 — Test coverage
- R8.1 — Service tests (7): valid PENDING→PROCESSING, PROCESSING→SHIPPED, SHIPPED→DELIVERED;
  invalid transitions from PENDING/PROCESSING/SHIPPED; terminal DELIVERED and CANCELLED raise;
  not-found raises.
- R8.2 — Router tests (4): 200 on valid transition, 422 on invalid transition, 404 when not found,
  422 on unrecognized status string.
- R8.3 — Combination matrix (in `tests/orders/test_combinations.py`): exhaustive 5×5 matrix — all
  3 valid and all 22 invalid transitions tested individually.
- R8.4 — MCP tool tests (5): invalid UUID raises ValueError, invalid status raises ValueError,
  order not found raises ValueError, invalid transition raises ValueError, valid transition returns dict.
- R8.5 — Integration tests (8): full lifecycle via PATCH, terminal DELIVERED/CANCELLED blocks,
  step-skipping returns 422, 404 on nonexistent order, 422 on invalid UUID in path, 422 on bad
  status string, cross-user protection returns 404.

## Out of scope
- No change to the scheduler (it continues to promote PENDING → PROCESSING).
- No new order statuses beyond the existing five.
- No webhook notifications on status change.
- No audit log for status transitions.
