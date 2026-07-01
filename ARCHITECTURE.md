# EC-OPS: Architecture & Decision Record

This document covers the system architecture and the engineering decisions made across all build phases.

For a detailed rationale of every tool choice plus a technical Q&A section, see
[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

---

## What was built

### Application (Phases 1–3)

| Phase | Task | Deliverable |
|-------|------|-------------|
| 1 | T001 | Project scaffold — FastAPI app, uv, ruff, health endpoint |
| 1 | T002 | Database layer — SQLAlchemy models, async engine, Alembic migrations, pgvector stub |
| 1 | T003 | Order service — pure business logic, domain exceptions |
| 1 | T004 | REST API router — 5 routes (POST, GET, GET list, PATCH status, DELETE), FastAPI dependency injection, unit + integration tests |
| 1 | T005 | Background scheduler — APScheduler PENDING→PROCESSING every 5 min |
| 1 | T006 | Test suite consolidation — shared DB fixtures in conftest.py |
| 2 | T007 | MCP server — 7 tools wrapping service functions (create/get/list/cancel/find-by-product/update-status/search) |
| 2 | T008 | A2A agent endpoint — NL task submission, fire-and-forget background executor |
| 3 | T009 | AG-UI SSE stream — ordered RunStarted/TextDelta/ToolCallStart/ToolCallResult/RunFinished |
| 3 | T010 | A2UI ui_action events — order cards embedded in the SSE stream |
| 3 | T011 | Chat frontend — zero-build-step HTML/JS consuming the SSE stream |

### Authentication (Phase 5)

| Task | Deliverable |
|------|-------------|
| JWT auth module | `src/auth/` — models, schemas, service, dependencies, router |
| Users table migration | `migrations/versions/0003_add_users_table.py` |
| Initial user seeding | `scripts/seed_user.py` — idempotent, CLI or env-var driven |

### Developer tooling (Phase 4)

| Deliverable | Location | Purpose |
|---|---|---|
| Setup script | `scripts/setup.py` | One-command prereq check, install, DB setup, user seed, server start, and onboarding guide |
| Insomnia generator | `scripts/generate_insomnia.py` | Converts `requests/*.http` files into an Insomnia v4 collection |
| Insomnia collection | `requests/EC-OPS.insomnia_collection.json` | Single-file importable collection with auto-token-save after login |
| CI workflow | `.github/workflows/ci.yml` | Lint + tests on every PR/push via Tailscale to local Postgres |
| CI guide | `docs/ci-tailscale.md` | Step-by-step Tailscale auth key and secrets setup |
| Design decisions | `DESIGN_DECISIONS.md` | Tool rationale, alternatives, and technical Q&A |

### Agent harness (Phase 6)

| Deliverable | Location | Purpose |
|---|---|---|
| Guardrails module | `src/agent/guardrails.py` | `InputGuardrail` (pre-LLM) + `ToolOutputGuardrail` (post-tool, pre-LLM) + `OutputSanitizer` (post-LLM) |
| System prompt | `src/agent/agui_stream.py`, `src/agent/executor.py` | Constrains model scope and prevents internal data leakage |
| Per-tool call cap | Both pipelines | Stops runaway tool loops (>3 calls to same tool → user message) |
| Tool error recovery | Both pipelines | `is_error: true` in tool_results so model handles failures gracefully |
| Eval test suite | `tests/eval/` | 102 deterministic guardrail + pipeline evaluation tests (`@pytest.mark.eval`) |
| Auth enforcement tests | `tests/auth/test_agent_route_auth.py` | 12 tests: 7 verifying 401 on all agent/A2A routes + 5 `_resolve_token` unit tests |
| Guardrail wiring tests | `tests/agent/test_guardrail_wiring.py` | SSE event shape when guardrail blocks; A2A guardrail via HTTP |
| MCP tool tests | `tests/agent/test_mcp_server.py` | 7-tool inventory check + per-tool happy/error-path tests |
| Integration tests | `tests/integration/` | 61 tests across 4 files; all HTTP-only, no DB shortcuts; auto-skipped without `TEST_DATABASE_URL` |
| DEBUG logging | `src/core/config.py`, `src/main.py` | `LOG_LEVEL=DEBUG` traces full LM Studio request/response cycle |
| VS Code config | `.vscode/` | `launch.json` (5 run configs) + `tasks.json` (8 tasks) + `settings.json` (pytest, test explorer) |

### Bug fixes & hardening (Phase 7)

| Deliverable | Location | Purpose |
|---|---|---|
| `_ReasoningFilter.flush()` | `src/agent/agui_stream.py` | Prevents silent text loss when model never closes a `<think>` tag |
| ToolCallStart guard | `src/agent/agui_stream.py` | Count check moved before `yield ToolCallStart` — no dangling events |
| UUID parse guard | `src/agent/tools.py` | `ValueError` on invalid UUID string from LLM (before DB call) |
| Exception UUID truncation | `src/orders/exceptions.py` | `OrderNotFound`/`OrderNotCancellable` truncate ID to 8 chars |
| Executor fallback text | `src/agent/executor.py` | Non-empty response when `end_turn` has no text block |
| Task handle store | `src/agent/a2a_router.py` | `asyncio.Task` pinned in `_task_handles` — survives SIGTERM/reload |
| `_TRACEBACK_RE` fix | `src/agent/guardrails.py` | Non-greedy regex stops at blank line — preserves text after traceback |
| Integration test skip guard | `tests/orders/test_models.py`, `tests/orders/test_service.py` | `skipif` requires `TEST_DATABASE_URL` — can no longer accidentally target the app DB |

---

## System overview

```
Browser (frontend/)
       │  GET /  →  index.html / app.js / styles.css (StaticFiles)
       │  GET /agent/stream?message=…&token=<jwt>  →  SSE (AG-UI protocol)
       │  Authorization: Bearer <jwt>  (all other endpoints)
       │
  FastAPI app (src/main.py)
       │
       ├── /auth router        POST /auth/register, POST /auth/token  (public)
       │      └── get_current_user()  ←  JWT dependency (all protected routes)
       │
       ├── /orders router      POST/GET/PATCH/DELETE  (requires get_current_user)
       ├── /agent/stream       AG-UI SSE → LM Studio (requires get_current_user)
       ├── /a2a/tasks          A2A task submission & polling (requires get_current_user)
       ├── /.well-known/agent.json   A2A Agent Card (requires get_current_user)
       │
       ├── APScheduler         promote_pending_orders() every 5 min
       │
       └── get_session()       AsyncSession per request (commit/rollback)
              │
         PostgreSQL (asyncpg)
              │
         orders / order_items / order_embeddings / users tables
```

```
Agent call path — AG-UI (/agent/stream):
  message → stream_executor
           → InputGuardrail.check()        [length / injection / scope]
           │   blocked? → TextDelta(rejection) + RunFinished — LM Studio never called
           │   pass ↓
           → AsyncAnthropic(base_url=LM_STUDIO)  [Anthropic-compat]
           → _ReasoningFilter  (strips <think>…</think> before TextDelta)
           → FastMCP tools → service functions → DB
           → ToolOutputGuardrail.scan()    [each tool result; injection in data → safe replacement]
           → ui_action events (order cards) for create/get tool results
           → OutputSanitizer (UUIDs truncated, tool names hidden, tracebacks removed)

Agent call path — A2A (/a2a/tasks/send):
  message → run_executor
           → InputGuardrail.check()        [before Anthropic client even created]
           │   blocked? → ExecutionResult(blocked=True) — task completes with rejection
           │   pass ↓
           → AsyncAnthropic(base_url=LM_STUDIO)
           → FastMCP tools → service functions → DB
           → ToolOutputGuardrail.scan()    [each tool result]
           → OutputSanitizer on final text
```

---

## Decision record

### 1. uv as package manager

**Decision:** Use `uv` instead of pip/Poetry/PDM.

**Why:** uv resolves and installs in milliseconds. `uv sync` is deterministic from `uv.lock`. `uv run <cmd>` removes virtualenv activation entirely.

---

### 2. SQLAlchemy async ORM with `mapped_column` typed API

**Decision:** `AsyncSession`, `async_sessionmaker`, SQLAlchemy 2.x `Mapped[T]` / `mapped_column()`.

**Why:** Full static type coverage without stubs. `expire_on_commit=False` prevents DetachedInstanceError. Single source of truth in `models.py`.

---

### 3. UUID primary keys

**Decision:** `UUID(as_uuid=True)` with `default=uuid.uuid4` for all PKs.

**Why:** Opaque to callers (no volume leakage). Globally unique without a DB sequence. Native Python `uuid.UUID` objects throughout.

---

### 4. Async all the way down (`asyncpg`)

**Decision:** `asyncpg` driver, every DB call async.

**Why:** FastAPI is ASGI. A synchronous DB call holds the event loop for its entire round-trip. `asyncpg` yields the loop during I/O. APScheduler's `AsyncIOScheduler` shares the same loop with no threading conflicts.

---

### 5. Layered architecture: models → service → router

**Decision:** Strict three-layer separation. Service functions accept `AsyncSession` directly (no HTTP knowledge).

**Why:** Each layer is independently testable. Service functions are reused by the REST router, MCP tools, A2A executor, and AG-UI stream — with no duplication. Swapping any layer doesn't touch the others.

---

### 6. `get_session` dependency with commit/rollback semantics

**Decision:** `src/core/dependencies.py` commits on success and rolls back on exception — automatically for every route.

**Why:** No per-route try/except boilerplate. New routes are safe by default. Overridable via `app.dependency_overrides` for tests.

---

### 7. Domain exceptions (`OrderNotFound`, `OrderNotCancellable`, `OrderStatusTransitionError`)

**Decision:** Typed domain exceptions from service layer, mapped to HTTP in router.

**Why:** The service is protocol-agnostic. The MCP tool catches `OrderNotFound` and raises `ValueError`. The router raises `HTTPException(404)`. Same domain concept, correct protocol translation per caller.

`OrderStatusTransitionError` is raised when `PATCH /orders/{id}/status` is called with a transition that violates the state machine (e.g. PENDING → SHIPPED, or any transition from a terminal status). The router maps it to 422; the MCP tool wraps it as `ValueError` so the LLM receives a readable error message rather than a raw Python exception.

---

### 7a. State machine for status transitions (`PATCH /orders/{id}/status`)

**Decision:** A `_VALID_TRANSITIONS` dict in `src/orders/service.py` encodes every permitted status change as a data structure. The `update_order_status()` service function checks membership before mutating the row; an invalid transition raises `OrderStatusTransitionError`.

```
PENDING     → {PROCESSING}          (scheduler only; also allowed via PATCH for manual override)
PROCESSING  → {SHIPPED}
SHIPPED     → {DELIVERED}
DELIVERED   → {}   ← terminal
CANCELLED   → {}   ← terminal
```

**Why:**
- A dict lookup is O(1) and the entire policy is auditable at a glance — no nested `if/elif` chains scattered across the codebase.
- New statuses require only a one-line dict change rather than hunting down every branch.
- Terminals are represented explicitly as empty sets, so the guard `if new_status not in _VALID_TRANSITIONS[old_status]` handles them without special cases.
- The same dict is used whether the caller is the REST router, an MCP tool, or a future service endpoint.

---

### 8. Cancel = soft delete (CANCELLED status, record retained)

**Decision:** `cancel_order` sets `order.status = CANCELLED` and `order.updated_at = now()`.
The row is never deleted. Migration `0002_add_cancelled_status` adds the enum value.

**Why:** Retaining cancelled orders enables audit trails — reporting on cancellation
rates, customer behaviour, and order history requires the record to exist after
cancellation. A GET on a cancelled order returns its full state with `status: CANCELLED`
rather than 404. The CANCELLED status is terminal: attempting to cancel an already-
CANCELLED order raises `OrderNotCancellable` (same as PROCESSING). The service interface
(`cancel_order` signature, exception types) is unchanged; the only behavioural difference
is that the row survives and `GET /orders?status=CANCELLED` surfaces it.

---

### 9. APScheduler with `AsyncIOScheduler`, `coalesce=True`, `max_instances=1`

**Decision:** Scheduler started/stopped in FastAPI lifespan.

**Why:** `AsyncIOScheduler` runs jobs as coroutines on the main event loop — same `asyncpg` pool, no threads. `coalesce=True` prevents N missed runs firing consecutively. `max_instances=1` prevents concurrent bulk UPDATEs generating table-level lock contention.

---

### 10. Core-level bulk UPDATE in scheduler

**Decision:** `update(Order).where(...).values(...)` — not ORM flush.

**Why:** At N PENDING orders, ORM flush sends N+1 queries. Core UPDATE sends 1. It's also atomic at the DB level — no window between SELECT and UPDATE where new inserts get missed. `updated_at` is set explicitly because `onupdate=func.now()` only fires on ORM flush, not Core statements.

---

### 11. LM Studio via Anthropic-compat endpoint

**Decision:** `AsyncAnthropic(base_url=settings.lmstudio_base_url)` — zero SDK change, just a URL redirect.

**Why:** LM Studio's `/v1/messages` endpoint is Anthropic-SDK-compatible. No OpenAI SDK import, no provider abstraction layer, no extra dependency. Config-driven: change `LMSTUDIO_BASE_URL` and `LM_MODEL` in `.env` to switch models or point at a remote server.

---

### 12. `_ReasoningFilter` for streaming text

**Decision:** Stateful per-turn filter strips `<think>…</think>` blocks before yielding `TextDelta` events.

**Why:** Reasoning models (phi-4-mini-reasoning, DeepSeek-R1, QwQ) emit chain-of-thought tokens before tool calls and final answers. Without filtering, those tokens stream verbatim into the chat bubble — exposing internal reasoning to the user and making the UI look broken. The filter is chunk-boundary-safe: it buffers partial tags across chunks so nothing leaks regardless of how the model streams.

**Tradeoff:** Use a non-reasoning instruct model (phi-4, qwen2.5-instruct) as the primary choice — the filter is then a safety net only, not load-bearing. Reasoning models burn 300–500 thinking tokens per turn even for simple queries, which adds latency at 6 tok/s on CPU.

---

### 13. `NullPool` for test isolation

**Decision:** Integration tests use `create_async_engine(..., poolclass=NullPool)`.

**Why:** Default pool caches connections with event-loop affinity. pytest-asyncio creates a new loop per test. Reusing a cached connection across loops raises `"Future attached to a different loop"`. `NullPool` creates a fresh connection per `async with engine.begin()` — no loop affinity, full isolation. Production engine uses the default pool.

---

### 15. Bug audit — architectural findings not yet fixed

These issues were identified during a full line-by-line audit but require deployment decisions:

| Issue | Severity | Fix path |
|---|---|---|
| A2A `_tasks` dict is per-process — tasks posted to worker A are invisible to worker B | CRITICAL | Use Redis or DB-backed task store for multi-worker deployments |
| JWT `?token=` for SSE clients appears in server access logs | MEDIUM | Implement short-lived SSE ticket exchange; log redaction via proxy |
| `order_items.order_id` FK column has no explicit index | MEDIUM | `index=True` on the mapped column + Alembic migration |
| Default `JWT_SECRET_KEY` not rejected at startup | HIGH | Startup guard: raise `RuntimeError` if key equals the default literal |
| 24-hour JWT expiry with no revocation mechanism | LOW | Reduce to 60–120 min or add JTI blocklist |

---

### 14. `dotenv_values()` instead of `load_dotenv()` in tests

**Decision:** Read `.env` with `dotenv_values()` into a local dict. Never `load_dotenv()` in test files.

**Why:** `load_dotenv()` mutates `os.environ` as a side effect. If `DATABASE_URL` is in `.env`, it becomes visible to every other test module in the same process — including tests gated on `os.environ.get("DATABASE_URL")` to skip live-DB runs. Those skip guards stop working and tests start failing in environments without a production DB. `dotenv_values()` has no side effects.

---

### 15. Pydantic field validators on request schemas

**Decision:** `customer_name: str = Field(min_length=1)`, `items: list[...] = Field(min_length=1)`, `quantity: int = Field(gt=0)`, `price: Decimal = Field(ge=Decimal("0"))`, `product_name: str = Field(min_length=1)`.

**Why:** FastAPI returns 422 automatically on violation — no custom error handling code. Without these, the DB would accept empty customer names, empty item lists, zero-quantity items, and negative prices, producing nonsense data. Validation at the API boundary keeps the service and DB clean. Tested explicitly with 422 assertions.

---

### 17. `scripts/db_setup.py` — single-command database bootstrap

**Decision:** One Python script that creates the app and test databases, enables pgvector, and runs Alembic migrations. No shell scripts, no manual psql commands.

**Why:** New developers need three things before the app starts: two databases exist, pgvector is enabled, and the schema is current. Without a script, setup requires knowing PostgreSQL CLI syntax, running four separate commands, and understanding the right order. The script reads `DATABASE_URL` and `TEST_DATABASE_URL` directly from `.env`, uses asyncpg (already a project dependency — no extra install), and is idempotent (re-running is safe). This reduces onboarding from "follow these manual steps" to `uv run python scripts/db_setup.py`.

**Tradeoff:** The script uses asyncpg directly rather than wrapping psql, so it must connect to the PostgreSQL `postgres` system database first (to issue `CREATE DATABASE` outside a transaction). The connection string is derived by substituting the target database name with `postgres` — this works as long as the user/password have `CREATEDB` privileges.

---

### 16. Shared DB fixtures in `tests/conftest.py`

**Decision:** All DB infrastructure in `conftest.py`. `TRUNCATE orders CASCADE` between tests.

**Why:** `CASCADE` propagates to `order_items` and `order_embeddings` via FK — a single statement clears all three tables. `_TABLES_CREATED` flag ensures `CREATE IF NOT EXISTS` runs once per process, not per test. `autouse=True` `db_setup` fixture skips all DB work if `TEST_DATABASE_URL` is absent, keeping unit tests runnable anywhere.

---

### 18. JWT Bearer authentication (`python-jose` + `bcrypt`)

**Decision:** HS256 JWT tokens, 24-hour expiry, dual token extraction (Authorization header + `?token=` query param). `bcrypt` used directly; `passlib` removed.

**Why:**
- Stateless tokens require no session store — the server validates the signature and expiry locally on every request.
- HS256 with a single secret key is sufficient for a single-service deployment and trivial to rotate.
- `passlib 1.7.4` is incompatible with `bcrypt ≥ 5.0` (`AttributeError: module 'bcrypt' has no attribute '__about__'`). Using `bcrypt` directly eliminates the broken dependency chain without loss of functionality.
- Browser `EventSource` cannot set custom request headers, so the SSE endpoint (`/agent/stream`) accepts the token as a `?token=` query parameter as a fallback. The `_resolve_token` dependency checks the header first; the query param is only used when the header is absent.
- `OAuth2PasswordRequestForm` for `POST /auth/token` follows the standard OAuth2 password-flow spec and makes the Swagger UI "Authorize" button work out of the box.

**Scope:** Every endpoint except `GET /health` is protected via `get_current_user = Depends(...)`. The auth module lives in `src/auth/` (models, schemas, service, dependencies, router). Migration `0003_add_users_table` adds the `users` table. `scripts/seed_user.py` creates the initial admin account.
