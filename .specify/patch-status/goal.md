# Feature Goal — patch-status

## User goal
An operator (via REST API or AI agent) can advance an order through the complete fulfilment
lifecycle — PROCESSING → SHIPPED → DELIVERED — using a single endpoint. Invalid transitions
are rejected immediately with a clear error. The AI agent has the same capability as the REST
API (feature parity across stack).

## Success signals
- [x] S1: `PATCH /orders/{id}/status` with body `{"status": "SHIPPED"}` on a PROCESSING order
      returns 200 with the updated order (status=SHIPPED, updated_at set).
- [x] S2: Attempting an invalid transition (e.g. PENDING → DELIVERED, or any PATCH on a DELIVERED
      or CANCELLED order) returns 422.
- [x] S3: A PATCH on a non-existent order ID returns 404.
- [x] S4: A PATCH with an unrecognized status string returns 422.
- [x] S5: All 3 valid transitions (PENDING→PROCESSING, PROCESSING→SHIPPED, SHIPPED→DELIVERED)
      and all 22 invalid transitions across the 5×5 matrix are covered by deterministic tests.
- [x] S6: The AI agent can advance an order's status via `update_order_status_tool`.
- [x] S7: `update_order_status_tool` raises readable ValueError (not raw Python exception) for
      invalid UUID, invalid status string, not-found order, or invalid transition.
- [x] S8: `update_order_status_tool` is listed in the MCP server's tool inventory (7 tools total).
- [x] S9: The guardrail `_TOOL_NAMES` frozenset recognizes `update_order_status_tool`.

## Spec coverage
S1 → spec req: R4, R5.1, R5.2
S2 → spec req: R2, R3, R5.3
S3 → spec req: R4.2, R5.4
S4 → spec req: R1.2, R5.5
S5 → spec req: R2.3, R8.3
S6 → spec req: R6.1, R6.6
S7 → spec req: R6.3, R6.4, R6.5
S8 → spec req: R6.1
S9 → spec req: R7.1

## Goal progress
All signals complete — feature shipped.
