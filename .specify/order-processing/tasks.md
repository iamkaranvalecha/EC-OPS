# Tasks

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — Project scaffold
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (foundation for all core features)
- **Scope**: pyproject.toml, .env.example, .gitignore, README.md, src/__init__.py, src/main.py, src/core/__init__.py, src/core/config.py, src/orders/__init__.py, src/scheduler/__init__.py, src/agent/__init__.py, tests/__init__.py, tests/conftest.py
- **Done when**:
  - `uv sync` resolves all dependencies (fastapi, sqlalchemy, asyncpg, alembic, apscheduler, mcp, anthropic, pgvector, pytest, pytest-asyncio, httpx, ruff).
  - `uv run ruff check src tests` exits 0.
  - `uv run uvicorn src.main:app` boots and `GET /health` returns 200.
- **Goal signals**: S1, S2, S3, S4, S5
- **Status**: [x]

## T002 — Database layer + models
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (create / retrieve / list / cancel persistence)
- **Scope**: src/core/database.py, src/orders/models.py, src/orders/schemas.py, src/core/retrieval.py, alembic.ini, migrations/env.py, migrations/versions/0001_create_orders.py, tests/orders/test_models.py
- **Done when**:
  - `Order` and `OrderItem` SQLAlchemy models exist with an `OrderStatus` enum (PENDING, PROCESSING, SHIPPED, DELIVERED) and snake_case columns/tables.
  - Async engine + `async_session` factory defined in src/core/database.py.
  - Migration enables `pgvector` extension (`CREATE EXTENSION IF NOT EXISTS vector`) and creates `order_embeddings` table (id, order_id FK, embedding vector(1536), content text, created_at).
  - `uv run alembic upgrade head` creates `orders`, `order_items`, and `order_embeddings` tables.
  - `src/core/retrieval.py` provides two async stubs: `ingest_order_embeddings(order_id, session)` (no-op, logs "embedding not wired") and `retrieve_similar_orders(query, session, top_k=5) -> list` (returns []).
  - `uv run pytest tests/orders/test_models.py` passes: inserts an order with multiple items and reads them back; asserts order_embeddings table exists.
- **Goal signals**: S1, S2, S3, S4
- **Status**: [x]

## T003 — Order service (business logic)
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (create / retrieve / list / cancel rules)
- **Scope**: src/orders/service.py, src/orders/exceptions.py, tests/orders/test_service.py
- **Done when**:
  - `create_order`, `get_order`, `list_orders(status=None)`, `cancel_order` are async functions accepting an AsyncSession (no HTTP).
  - `cancel_order` raises `OrderNotCancellable` when order status is not PENDING.
  - `get_order` raises `OrderNotFound` for unknown IDs.
  - `uv run pytest tests/orders/test_service.py` passes: covers happy paths, status filtering, cancel-non-PENDING rejection, and not-found.
- **Goal signals**: S1, S2, S3, S4
- **Status**: [x]

## T004 — REST API router
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (API surface for all core operations)
- **Scope**: src/orders/router.py, src/core/dependencies.py, src/main.py, tests/orders/test_router.py, tests/integration/test_orders_api.py
- **Done when**:
  - Routes wired into app: `POST /orders` (201 + id), `GET /orders/{id}` (200 / 404), `GET /orders?status=` (200 filtered), `DELETE /orders/{id}` (204 on PENDING, 409 otherwise).
  - `get_session` dependency provides an async session per request.
  - `uv run pytest tests/orders/test_router.py` passes (handler-level).
  - `uv run pytest tests/integration/test_orders_api.py` passes: httpx client against a real test DB walks create → get → list → cancel and asserts 409 when cancelling a non-PENDING order.
- **Goal signals**: S1, S2, S3, S4
- **Issue**: #4
- **Status**: [x]

## T005 — Background scheduler
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (auto-promote PENDING → PROCESSING every 5 minutes)
- **Scope**: src/scheduler/jobs.py, src/scheduler/setup.py, src/main.py, tests/scheduler/test_jobs.py
- **Done when**:
  - APScheduler is started/stopped inside the FastAPI lifespan.
  - Job `promote_pending_orders` is registered on a 5-minute interval and sets all PENDING orders to PROCESSING.
  - `uv run pytest tests/scheduler/test_jobs.py` passes: directly invokes the job against seeded data, asserting PENDING → PROCESSING and that PROCESSING/SHIPPED/DELIVERED orders are unchanged.
- **Goal signals**: S5
- **Issue**: #6
- **Status**: [x]

## T006 — Test suite consolidation + coverage
- **Phase**: 1
- **Milestone**: mvp
- **Spec req**: 1 (verify all core features green together)
- **Scope**: tests/conftest.py, tests/integration/test_orders_api.py, tests/scheduler/test_jobs.py
- **Done when**:
  - Shared async DB fixtures (engine, session, app client, DB setup/teardown) live in tests/conftest.py.
  - `uv run pytest` is fully green across unit + integration + scheduler tests.
  - `uv run ruff check` passes repo-wide.
- **Goal signals**: S1, S2, S3, S4, S5
- **Issue**: #8
- **Status**: [x]

## T007 — MCP server
- **Phase**: 2
- **Milestone**: mvp
- **Spec req**: 2 (MCP)
- **Scope**: src/agent/mcp_server.py, src/agent/tools.py, tests/agent/test_mcp_server.py
- **Done when**:
  - MCP server (official `mcp` Python SDK) registers `create_order`, `get_order`, `list_orders`, `cancel_order`, and `search_orders` as tools that delegate to src/orders/service and src/core/retrieval respectively.
  - `search_orders` stub tool accepts a `query: str` and `top_k: int = 5` parameter and returns the result of `retrieve_similar_orders()` (empty list until embeddings are wired — stub is correct behaviour for now).
  - Server is runnable as a standalone process (e.g. `uv run python -m src.agent.mcp_server`).
  - `uv run pytest tests/agent/test_mcp_server.py` passes: lists tools (asserts all five present) and invokes one CRUD tool end-to-end against the test DB.
- **Goal signals**: S6
- **Issue**: #10
- **Status**: [x]

## T008 — A2A agent endpoint
- **Phase**: 2
- **Milestone**: mvp
- **Spec req**: 2 (A2A)
- **Scope**: src/agent/a2a_router.py, src/agent/executor.py, src/main.py, tests/agent/test_a2a.py, tests/integration/test_a2a_flow.py
- **Done when**:
  - `GET /.well-known/agent.json` returns a valid A2A Agent Card describing the order skills.
  - `POST /a2a/tasks/send` accepts a natural-language message and `GET /a2a/tasks/{id}` returns task state and result.
  - Claude-backed executor (claude-sonnet-4-6) maps NL intent → order tool calls.
  - `uv run pytest tests/agent/test_a2a.py tests/integration/test_a2a_flow.py` passes: a "create an order" task results in a created order (executor mocked for determinism).
- **Goal signals**: S7
- **Issue**: #12
- **Status**: [x]

## T009 — AG-UI SSE stream
- **Phase**: 3
- **Milestone**: mvp
- **Spec req**: 2 (AG-UI)
- **Scope**: src/agent/agui_stream.py, src/agent/events.py, src/main.py, tests/agent/test_agui_stream.py
- **Done when**:
  - `GET /agent/stream` responds with `text/event-stream`.
  - Emits AG-UI events in order: RunStarted, TextDelta, ToolCallStart, ToolCallResult, RunFinished.
  - `uv run pytest tests/agent/test_agui_stream.py` passes: consumes the SSE stream for a sample prompt and asserts the ordered event types.
- **Goal signals**: S8
- **Issue**: #14
- **Status**: [x]

## T010 — A2UI ui_action events
- **Phase**: 3
- **Milestone**: mvp
- **Spec req**: 2 (A2UI)
- **Scope**: src/agent/events.py, src/agent/agui_stream.py, tests/agent/test_a2ui_events.py
- **Done when**:
  - Agent emits CustomEvent blocks with `type: ui_action` (order cards, status badges) embedded in the AG-UI SSE stream.
  - `uv run pytest tests/agent/test_a2ui_events.py` passes: asserts a `ui_action` event carrying an order payload is emitted after a successful order tool call.
- **Goal signals**: S8, S9
- **Status**: [ ]

## T011 — Chat frontend
- **Phase**: 3
- **Milestone**: mvp
- **Spec req**: 2 (AG-UI + A2UI)
- **Scope**: frontend/index.html, frontend/app.js, frontend/styles.css
- **Done when**:
  - index.html runs with no build step and opens an EventSource to `/agent/stream`.
  - Renders streaming text deltas, tool-call status, and `ui_action` cards (order details + status badges) live.
  - Manual run shows a chat that creates and displays an order via the agent.
- **Goal signals**: S9
- **Status**: [ ]
