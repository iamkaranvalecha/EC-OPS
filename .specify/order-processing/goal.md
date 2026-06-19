# Feature Goal

## User goal
A user can place, track, list, and cancel orders both through a REST API and by chatting with an AI agent that performs those operations live in the UI.

## Success signals
<!-- Each signal is an observable user-facing outcome. Checked off by the orchestrator after each phase. -->
- [ ] S1: POST /orders creates an order and returns its ID
- [ ] S2: GET /orders/{id} returns full order details
- [ ] S3: GET /orders returns all orders, filterable by status
- [ ] S4: DELETE /orders/{id} cancels a PENDING order; rejects non-PENDING with 409
- [ ] S5: Background job promotes PENDING → PROCESSING every 5 minutes (verified by test)
- [ ] S6: MCP server exposes all four order operations as callable tools
- [ ] S7: A2A agent accepts a natural-language task and executes the correct order operation
- [ ] S8: AG-UI /agent/stream SSE endpoint streams agent events to the chat frontend
- [ ] S9: Chat frontend renders agent responses and UI-action cards live

## Spec coverage
<!-- Maps each signal to the spec requirements it satisfies -->
S1 → spec req: 1 (Create an order)
S2 → spec req: 1 (Retrieve order details)
S3 → spec req: 1 (List all orders, optional status filter)
S4 → spec req: 1 (Cancel an order, only if PENDING)
S5 → spec req: 1 (Background job PENDING → PROCESSING every 5 min)
S6 → spec req: 2 (MCP)
S7 → spec req: 2 (A2A)
S8 → spec req: 2 (AG-UI)
S9 → spec req: 2 (AG-UI + A2UI)

## Goal progress
<!-- Updated by orchestrator after each phase completes -->
(not started)
