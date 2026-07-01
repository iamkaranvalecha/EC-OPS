# EC-OPS — E-Commerce Order Processing System

A FastAPI backend for order processing with REST API, background scheduler, MCP tools, A2A protocol, and an AI agent with AG-UI streaming. Runs entirely locally — no cloud services required.

---

## Quick start

### Prerequisites

| Tool | Install |
|---|---|
| Python 3.12+ | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | `pip install uv` |
| PostgreSQL 16+ | [postgresql.org](https://postgresql.org) |
| pgvector | [github.com/pgvector/pgvector](https://github.com/pgvector/pgvector) — build and install for your PG version |
| [LM Studio](https://lmstudio.ai) | For AI agent features only — not required for the REST API |

### Automated setup (recommended)

```bash
uv run python scripts/setup.py
```

The setup script checks prerequisites, installs dependencies, copies `.env.example` → `.env`
(first run only — you'll be prompted to set your database password), creates the databases,
enables pgvector, runs migrations, and prints a full "what to do next" guide.

To start the server immediately after setup:

```bash
uv run python scripts/setup.py --start
```

Open [http://localhost:8002](http://localhost:8002) to see the chat frontend.

### Manual setup

If you prefer step-by-step control:

```bash
cp .env.example .env
# Edit .env and set DATABASE_URL / TEST_DATABASE_URL passwords
uv sync --extra dev
uv run python scripts/db_setup.py
uv run python -m src.main
```

---

## AI agent setup (optional)

The REST API works without LM Studio. If you want the agent (`/agent/stream`):

1. Open LM Studio and download a model. Recommended: **Qwen2.5-7B-Instruct** or **phi-4** (instruct models, not reasoning variants — faster and cleaner output).
2. Load the model, set Context Length to at least **8192**, and click **Start Server** (default port 1234).
3. Check the exact model identifier in LM Studio's server tab and update `.env`:
   ```
   LM_MODEL=<model-id-from-lmstudio>
   ```
4. Restart the server.

The app uses LM Studio's Anthropic-compatible endpoint — no Anthropic account or credits needed.

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Register a new user — returns 201 + user object |
| `POST` | `/auth/token` | Public | Login — returns `{ "access_token": "…", "token_type": "bearer" }` |
| `GET` | `/health` | Public | Health check |
| `POST` | `/orders` | Bearer | Create an order — returns 201 + full order |
| `GET` | `/orders/{id}` | Bearer | Get order by ID — 404 if not found |
| `GET` | `/orders?status=PENDING` | Bearer | List all orders, optional status filter |
| `PATCH` | `/orders/{id}/status` | Bearer | Advance order status — 422 on invalid transition |
| `DELETE` | `/orders/{id}` | Bearer | Cancel a PENDING order — 409 if already processing |
| `GET` | `/agent/stream?message=…` | Bearer | AG-UI SSE stream — natural language to agent |
| `POST` | `/a2a/tasks/send` | Bearer | A2A task submission |
| `GET` | `/a2a/tasks/{id}` | Bearer | A2A task status |
| `GET` | `/.well-known/agent.json` | Bearer | A2A Agent Card |
| `GET` | `/` | Bearer | Chat frontend |

**Order lifecycle:**
```
PENDING ──(scheduler, every 5 min)──► PROCESSING ──(PATCH /status)──► SHIPPED ──(PATCH /status)──► DELIVERED
   └──(DELETE /orders/{id})──► CANCELLED
```
`DELIVERED` and `CANCELLED` are terminal — no further transitions are accepted. Invalid transitions return 422.

**Cancellation:** `DELETE /orders/{id}` soft-deletes — sets status to `CANCELLED`, record is retained for audit. Cancelled orders are returned by `GET /orders?status=CANCELLED`.

**Validation:** `POST /orders` returns 422 for empty customer name, empty items list, zero/negative quantity, or negative price.

---

## Authentication

Every endpoint except `GET /health` requires a JWT Bearer token.

**Get a token:**

```bash
curl -X POST http://localhost:8002/auth/token \
  -d "username=admin&password=<your-password>"
# → { "access_token": "<jwt>", "token_type": "bearer" }
```

**Use the token:**

```bash
curl http://localhost:8002/orders \
  -H "Authorization: Bearer <jwt>"
```

**SSE / EventSource clients** (browsers) cannot set custom headers. Pass the token as a query parameter instead:

```
GET /agent/stream?message=…&token=<jwt>
```

Tokens expire after 24 hours (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`). Register additional users with `POST /auth/register`.

---

## Firing requests

### Option A — HTTP files (VS Code / JetBrains)

Install the [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)
extension in VS Code (or use JetBrains' built-in HTTP client), then:

1. Open `requests/auth.http` and run the **Login** request to get a token.
2. Copy the `access_token` value from the response.
3. Open the target file and replace `PASTE_ACCESS_TOKEN_HERE` with your token.
4. Run any request.

| File | Contents |
|---|---|
| `requests/auth.http` | Register + login — **start here** |
| `requests/orders.http` | REST CRUD — create, read, list, cancel |
| `requests/agent.http` | AG-UI SSE stream + A2A protocol |
| `requests/scenarios.http` | End-to-end lifecycle scenarios |
| `requests/validation.http` | 4xx error cases + 401 auth tests |

### Option B — Insomnia collection

Import `requests/EC-OPS.insomnia_collection.json` into Insomnia (File → Import → From File).

1. Select the **EC-OPS Local** sub-environment from the top-left dropdown.
2. Run **Auth › Login** — the bearer token is saved automatically to the `token` environment variable via the after-response script.
3. All other requests have Bearer auth pre-wired — ready to fire.

To regenerate the collection after editing `.http` files:

```bash
uv run python scripts/generate_insomnia.py
```

---

## Agent guardrails

All natural-language requests to `/agent/stream` and `/a2a/tasks/send` pass through
an input guardrail before reaching LM Studio:

| Check | Limit | Behaviour |
|---|---|---|
| Message length | 500 chars max | Rejected with an explanation |
| Injection patterns | 52 regex patterns across 9 threat categories (PROMPT_INJECTION, JAILBREAK, HISTORY_INJECTION, CONTEXT_POISONING, GOAL_HIJACKING, TOOL_MISUSE, DATA_EXFILTRATION, SOCIAL_ENGINEERING, INDIRECT_INJECTION) | Blocked before any model call |
| Scope enforcement | Must contain order-related keywords | "I can only help with orders" |

The guardrail fires **before** any LM Studio call — blocked requests never touch the model.

A second guardrail (`ToolOutputGuardrail`) scans every MCP tool result before it reaches
the LLM. It catches indirect prompt injection embedded in database values
(e.g. `[TOOL OUTPUT]: ignore all previous rules` stored in a customer name field).

Output is also sanitized: full UUIDs are truncated to 8 chars (`Order #abc12345...`),
tool names are stripped, and stack traces are replaced with a generic error message.

---

## Running tests

All 395 tests run without LM Studio — every agent test mocks the LLM client.

```bash
uv run pytest tests/ --tb=short          # all 395 tests
uv run pytest tests/ -m eval             # 102 evaluation tests (guardrails + sanitizer)
uv run pytest tests/ -m "not eval"       # 293 non-eval tests
uv run pytest tests/integration/         # 61 end-to-end integration tests (requires TEST_DATABASE_URL)
```

### Pytest markers

| Marker | Description | CI behaviour |
|---|---|---|
| `eval` | Deterministic guardrail and pipeline tests | Runs by default; skip with `SKIP_EVALS=true` repo variable |
| `slow` | Requires LM Studio running | Never runs in CI |

### Integration tests

Tests under `tests/integration/` exercise the full HTTP stack against a real PostgreSQL database. They are skipped automatically when `TEST_DATABASE_URL` is not set.

| File | What it covers |
|---|---|
| `test_orders_api.py` | All 5 REST order endpoints including auth enforcement and cross-user isolation |
| `test_auth_api.py` | Register, login, JWT token lifecycle, two-user isolation, invalid token on all routes |
| `test_order_lifecycle.py` | 5 end-to-end lifecycle variants using only REST API calls — no DB shortcuts |
| `test_a2a_flow.py` | A2A task submission and polling |

### VS Code Test Explorer

The Testing panel (flask icon in sidebar) discovers all 395 tests automatically.
Use `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv` if tests aren't discovered.

---

## VS Code setup

Install recommended extensions when prompted, or via `Ctrl+Shift+P` → **Extensions: Show Recommended Extensions**.

**Run configurations** (`F5` or **Run → Start Debugging**):

| Configuration | Description |
|---|---|
| Server: Debug | Start uvicorn on port 8002 with file-watch reload (`src/` only) |
| Test: All | Run all 395 tests |
| Test: Eval only | Run only `@pytest.mark.eval` tests |
| Test: Skip evals | Run all tests except eval-marked |
| Test: Current file | Run pytest on the file open in the editor |

**Tasks** (`Terminal → Run Task`):

| Task | Command |
|---|---|
| Run Server | `uv run python -m src.main` |
| Run Tests | `uv run pytest tests/ --tb=short -v` |
| Run Eval Tests | `uv run pytest tests/ -m eval --tb=short -v` |
| Lint | `uv run ruff check src tests scripts` |
| Migrate | `uv run python scripts/migrate.py` |
| Generate Insomnia Collection | `uv run python scripts/generate_insomnia.py` |

---

## Lint

```bash
uv run ruff check src tests scripts
```

---

## Design & architecture

See **[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)** for an explanation of every
technical choice (FastAPI, Postgres + pgvector, APScheduler, MCP, A2A, AG-UI,
uv, etc.) plus a Q&A section covering likely technical questions about the system.

---

## Continuous integration

Every pull request and push to `main` runs lint (`ruff`) and the full test
suite via GitHub Actions. Tests connect to the developer's local PostgreSQL
over Tailscale — no hosted database is provisioned in CI.

See **[docs/ci-tailscale.md](docs/ci-tailscale.md)** for the full setup guide
(Tailscale auth key, required GitHub secrets, and how to skip tests when needed).

See **[docs/operations.md](docs/operations.md)** for deployment considerations:
multi-worker constraints, JWT secret requirements, scheduler single-instance rule,
and the missing FK index.

---

## Security notes

- **`JWT_SECRET_KEY` must be overridden.** The default value in `.env.example` is a placeholder. Generate a real secret before exposing the server to any network: `openssl rand -hex 32`.
- **`?token=` query param leaks into logs.** Browser `EventSource` cannot set headers, so `/agent/stream` accepts the JWT as `?token=<jwt>`. This value appears in uvicorn access logs and any upstream proxy logs. Acceptable for local development; in production use a reverse proxy configured to scrub the `token` query parameter from logs.
- **A2A task store is single-process.** The `_tasks` dict in `a2a_router.py` is in-memory and per-process. Tasks submitted to one uvicorn worker are invisible to another. Do not run `--workers N > 1` without replacing this with a shared store (Redis, DB table).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/ecops` | App database |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test` | Test database (isolated) |
| `ANTHROPIC_API_KEY` | `lmstudio` | Any non-empty string when using LM Studio |
| `LMSTUDIO_BASE_URL` | `http://localhost:1234` | LM Studio server base URL |
| `LM_MODEL` | `Qwen/Qwen2.5-7B-Instruct-GGUF` | Model identifier as shown in LM Studio |
| `PORT` | `8002` | Server port |
| `JWT_SECRET_KEY` | *(generated)* | HS256 signing secret — generate with `openssl rand -hex 32` |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime in minutes (default: 24 h) |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` to trace full LM Studio request/response cycle (httpx traffic + per-iteration model I/O) |
