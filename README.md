# EC-OPS — E-Commerce Order Processing System

A FastAPI backend for order processing with MCP, A2A, AG-UI, and A2UI protocol support.

## Requirements

- Python 3.11+
- PostgreSQL 15+ with the [pgvector](https://github.com/pgvector/pgvector) extension installed
- [uv](https://docs.astral.sh/uv/) package manager

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Default in example | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:password@localhost:5432/ecops` | Async PostgreSQL connection string. Must use the `asyncpg` driver. |
| `ANTHROPIC_API_KEY` | `your-anthropic-api-key-here` | Anthropic API key (required for AI features). |

## Setup

```bash
uv sync --extra dev
cp .env.example .env
# edit .env with your DATABASE_URL and ANTHROPIC_API_KEY

# Enable pgvector in your Postgres database first:
# psql -d ecops -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Create tables
uv run alembic upgrade head

uv run uvicorn src.main:app --reload
```

### Database schema

Migrations live in `migrations/versions/`. The initial migration (`0001_create_orders`) creates three tables:

| Table | Purpose |
|---|---|
| `orders` | Core order records (`id`, `customer_name`, `status`, `created_at`, `updated_at`) |
| `order_items` | Line items linked to an order (`product_name`, `quantity`, `price`) |
| `order_embeddings` | 1536-dimension pgvector embeddings linked to an order (populated by retrieval stubs) |

`OrderStatus` values: `PENDING`, `PROCESSING`, `SHIPPED`, `DELIVERED`.

### Vector retrieval (stubs)

`src/core/retrieval.py` contains two async stubs:

- `ingest_order_embeddings(order_id, session)` — no-op; logs a message. Will populate `order_embeddings` once an embedding model is wired.
- `retrieve_similar_orders(query, session, top_k=5)` — returns `[]`. Will perform a pgvector similarity search once embeddings are available.

## Running tests

```bash
uv run pytest
```

## Linting

```bash
uv run ruff check src tests
```
