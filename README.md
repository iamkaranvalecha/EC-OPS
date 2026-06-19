# EC-OPS — E-Commerce Order Processing System

A FastAPI backend for order processing with REST API, background scheduler, MCP tools, A2A protocol, and an AI agent with AG-UI streaming. Runs entirely locally — no cloud services required.

---

## Quick start (3 steps)

### 1. Prerequisites

| Tool | Install |
|---|---|
| Python 3.12+ | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | `pip install uv` |
| PostgreSQL 16+ | [postgresql.org](https://postgresql.org) |
| pgvector | [github.com/pgvector/pgvector](https://github.com/pgvector/pgvector) — build and install for your PG version |
| [LM Studio](https://lmstudio.ai) | For AI agent features only — not required for the REST API |

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set your database password:

```
DATABASE_URL=postgresql+asyncpg://postgres:<your-password>@localhost:5432/ecops
TEST_DATABASE_URL=postgresql+asyncpg://postgres:<your-password>@localhost:5432/ecops_test
```

Everything else has working defaults.

### 3. Install, set up DB, and start

```bash
uv sync --extra dev
uv run python scripts/db_setup.py
uv run python -m src.main
```

`db_setup.py` creates the databases, enables pgvector, and runs migrations. Open [http://localhost:8002](http://localhost:8002) to see the chat frontend.

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

| Method | Path | Description |
|---|---|---|
| `POST` | `/orders` | Create an order — returns 201 + full order |
| `GET` | `/orders/{id}` | Get order by ID — 404 if not found |
| `GET` | `/orders?status=PENDING` | List all orders, optional status filter |
| `DELETE` | `/orders/{id}` | Cancel a PENDING order — 409 if already processing |
| `GET` | `/health` | Health check |
| `GET` | `/agent/stream?message=…` | AG-UI SSE stream — natural language to agent |
| `POST` | `/a2a/tasks/send` | A2A task submission |
| `GET` | `/a2a/tasks/{id}` | A2A task status |
| `GET` | `/.well-known/agent.json` | A2A Agent Card |
| `GET` | `/` | Chat frontend |

**Order lifecycle:** `PENDING` → `PROCESSING` (automatic, every 5 min) → `SHIPPED` → `DELIVERED`

**Validation:** `POST /orders` returns 422 for empty customer name, empty items list, zero/negative quantity, or negative price.

---

## Running tests

```bash
# Unit tests — no database required
uv run pytest tests/orders/test_router.py tests/orders/test_models.py \
              tests/orders/test_service.py tests/scheduler/ tests/agent/

# Full suite — requires both databases to be set up
uv run pytest
```

---

## Lint

```bash
uv run ruff check src tests
```

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
