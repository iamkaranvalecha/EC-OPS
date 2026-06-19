# Implementation Plan

Stack: Python 3.12 + FastAPI + pytest (pytest-asyncio + httpx) | DB: PostgreSQL (SQLAlchemy async ORM + asyncpg) | Auth: none | uv package manager | ruff lint

## Phase 1 — Core Backend
Milestone: mvp
Goal: REST API fully operational with PostgreSQL, background scheduler, and full test coverage.
Spec requirements covered: 1 (all core features — create, retrieve, list, cancel, status background job)
Success signals advanced: S1, S2, S3, S4, S5
Tasks: T001, T002, T003, T004, T005, T006

## Phase 2 — MCP + A2A Agent
Milestone: mvp
Goal: Order operations exposed as MCP tools and a working A2A-compatible agent endpoint that maps natural language to order tool calls.
Spec requirements covered: 2 (MCP, A2A)
Success signals advanced: S6, S7
Tasks: T007, T008

## Phase 3 — AG-UI + A2UI + Chat Frontend
Milestone: mvp
Goal: Streaming agent events over SSE with a live chat UI rendering responses and UI-action cards.
Spec requirements covered: 2 (AG-UI + A2UI)
Success signals advanced: S8, S9
Tasks: T009, T010, T011

---

## Phase 1 — Core Backend

### T001 — Project scaffold
- Spec req: 1 · Signals: S1–S5 (foundation)
- Scope: pyproject.toml, .env.example, .gitignore, README.md, src/__init__.py, src/main.py, src/core/__init__.py, src/core/config.py, src/orders/__init__.py, src/scheduler/__init__.py, src/agent/__init__.py, tests/__init__.py, tests/conftest.py
- Done when: `uv sync` resolves; `uv run ruff check src tests` passes; `uv run uvicorn src.main:app` boots and GET /health returns 200.

### T002 — Database layer + models
- Spec req: 1 + 3 (vector provisions) · Signals: S1, S2, S3, S4
- Scope: src/core/database.py, src/orders/models.py, src/orders/schemas.py, src/core/retrieval.py, alembic.ini, migrations/env.py, migrations/versions/0001_create_orders.py, tests/orders/test_models.py
- Done when: Order + OrderItem models defined with OrderStatus enum; async engine + session factory created; migration enables pgvector extension and creates `orders`, `order_items`, and `order_embeddings` (id, order_id FK, embedding vector(1536), content text) tables; retrieval.py provides ingest_order_embeddings and retrieve_similar_orders stubs; model test passes.

### T003 — Order service (business logic)
- Spec req: 1 · Signals: S1, S2, S3, S4
- Scope: src/orders/service.py, src/orders/exceptions.py, tests/orders/test_service.py
- Done when: create_order, get_order, list_orders(status?), cancel_order are pure async functions taking a session; cancel raises OrderNotCancellable for non-PENDING orders; unit tests (mocked/in-memory session) cover happy path + cancel-non-pending rejection.

### T004 — REST API router
- Spec req: 1 · Signals: S1, S2, S3, S4
- Scope: src/orders/router.py, src/core/dependencies.py, src/main.py, tests/orders/test_router.py, tests/integration/test_orders_api.py
- Done when: POST /orders (201 + id), GET /orders/{id} (200/404), GET /orders?status= (200 filtered list), DELETE /orders/{id} (204 on PENDING, 409 otherwise) wired into app; integration test (httpx + real test DB) walks the full create→get→list→cancel flow and asserts 409 on cancelling a non-PENDING order.

### T005 — Background scheduler
- Spec req: 1 · Signals: S5
- Scope: src/scheduler/jobs.py, src/scheduler/setup.py, src/main.py, tests/scheduler/test_jobs.py
- Done when: APScheduler started in FastAPI lifespan; job `promote_pending_orders` runs on a 5-minute interval and sets PENDING orders to PROCESSING; test invokes the job directly against a seeded PENDING order and asserts it becomes PROCESSING while non-PENDING orders are untouched.

### T006 — Test suite consolidation + coverage
- Spec req: 1 · Signals: S1–S5
- Scope: tests/conftest.py, tests/integration/test_orders_api.py, tests/scheduler/test_jobs.py
- Done when: `uv run pytest` is fully green across unit + integration + scheduler tests with shared async DB fixtures; `uv run ruff check` passes repo-wide.

## Phase 2 — MCP + A2A Agent

### T007 — MCP server
- Spec req: 2 (MCP) + 3 (vector stub) · Signals: S6
- Scope: src/agent/mcp_server.py, src/agent/tools.py, tests/agent/test_mcp_server.py
- Done when: MCP server (official `mcp` SDK) registers create_order, get_order, list_orders, cancel_order, and search_orders (stub — delegates to retrieve_similar_orders, returns [] until embeddings wired) as tools; runnable as standalone process; test lists tools (asserts all five present) and invokes one CRUD tool end-to-end against the test DB.

### T008 — A2A agent endpoint
- Spec req: 2 (A2A) · Signals: S7
- Scope: src/agent/a2a_router.py, src/agent/executor.py, src/main.py, tests/agent/test_a2a.py, tests/integration/test_a2a_flow.py
- Done when: GET /.well-known/agent.json returns a valid Agent Card; POST /a2a/tasks/send accepts an NL message and GET /a2a/tasks/{id} returns task state/result; Claude-backed executor (claude-sonnet-4-6) maps NL → order tool calls; integration test sends "create an order" style task and asserts an order is created (executor mocked for determinism).

## Phase 3 — AG-UI + A2UI + Chat Frontend

### T009 — AG-UI SSE stream
- Spec req: 2 (AG-UI) · Signals: S8
- Scope: src/agent/agui_stream.py, src/agent/events.py, src/main.py, tests/agent/test_agui_stream.py
- Done when: GET /agent/stream returns text/event-stream; emits RunStarted, TextDelta, ToolCallStart, ToolCallResult, RunFinished events per AG-UI spec; test consumes the SSE stream and asserts ordered event types for a sample prompt.

### T010 — A2UI ui_action events
- Spec req: 2 (A2UI) · Signals: S8, S9
- Scope: src/agent/events.py, src/agent/agui_stream.py, tests/agent/test_a2ui_events.py
- Done when: agent emits CustomEvent blocks with type `ui_action` (order cards, status badges) embedded in the SSE stream; test asserts a ui_action event with order payload is emitted after a successful order tool call.

### T011 — Chat frontend
- Spec req: 2 (AG-UI + A2UI) · Signals: S9
- Scope: frontend/index.html, frontend/app.js, frontend/styles.css
- Done when: index.html (no build step) opens an EventSource to /agent/stream; renders streaming text deltas, tool-call status, and ui_action cards (order details + status badges) live; manual run shows a chat that creates and displays an order via the agent.
