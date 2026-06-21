# EC-OPS — Operations Guide

This guide covers what changes when running EC-OPS beyond a single-developer local setup.

---

## Single-process constraint (A2A)

The A2A task store (`_tasks` dict in `src/agent/a2a_router.py`) is in-process memory.

**Impact:** With `uvicorn --workers N > 1`, a task POSTed to worker A is invisible when `GET /a2a/tasks/{id}` is handled by worker B — the caller gets a 404 even though the task exists.

**Workaround for now:** Run with a single worker (the default):
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8002
```

**Fix path:** Replace `_tasks` with a Redis hash or a `tasks` DB table.

---

## JWT secret key

The default `JWT_SECRET_KEY` in `.env.example` is a well-known placeholder. **Override it before exposing the server to any network:**

```bash
openssl rand -hex 32
# → paste the output into .env as JWT_SECRET_KEY=<value>
```

There is currently no startup guard — the server boots with the default key and issues forgeable tokens. Track issue: add a `RuntimeError` in `main.py` lifespan if the key equals the default.

---

## Token lifetime and revocation

`ACCESS_TOKEN_EXPIRE_MINUTES` defaults to `1440` (24 hours). There is no token revocation mechanism (no JTI blocklist, no `/auth/logout` endpoint).

To reduce the exposure window, set a shorter expiry in `.env`:
```
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

For revocation, a JTI blocklist would require a Redis set or a `revoked_tokens` DB table checked on every request.

---

## Scheduler — single instance only

`APScheduler` runs inside the FastAPI process with `max_instances=1`. If you run multiple uvicorn workers, each worker starts its own scheduler and you get concurrent bulk `UPDATE` statements every 5 minutes.

**Workaround:** Run the scheduler in exactly one process. Options:
- Single uvicorn worker (simplest).
- A dedicated `python -m src.scheduler.setup` process (if refactored out of `lifespan`).
- A distributed lock (e.g. `pg_try_advisory_lock`) acquired by the scheduler before running.

---

## Missing FK index

`order_items.order_id` has a FK constraint but no explicit B-tree index. PostgreSQL does not auto-index FK columns. As the `order_items` table grows, queries that filter by `order_id` (including SQLAlchemy's `selectin` relationship loading) become sequential scans.

**Fix:** Add `index=True` to the `order_id` mapped column in `src/orders/models.py` and generate an Alembic migration:
```bash
uv run alembic revision --autogenerate -m "add index on order_items.order_id"
uv run alembic upgrade head
```

---

## SSE token in query params

Browser `EventSource` cannot set custom headers, so `/agent/stream` accepts the JWT as `?token=<jwt>`. This value appears verbatim in uvicorn access logs and any upstream proxy logs.

**For production:** Configure the reverse proxy (nginx, Caddy) to redact the `token` query parameter from access logs. Long-term fix: implement a short-lived SSE ticket endpoint (`POST /auth/sse-ticket` → one-time token, 30s TTL) so the long-lived JWT never appears in URLs.

---

## LM Studio in production

LM Studio is a desktop app intended for local development. For any networked deployment:
- Point `LMSTUDIO_BASE_URL` at a dedicated inference server (vLLM, Ollama with `--host 0.0.0.0`, or a hosted API).
- Update `LM_MODEL` to match the model identifier on the new server.
- Remove or restrict `LOG_LEVEL=DEBUG` — it logs full HTTP traffic to the inference server.

---

## Environment variable reference

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | App database — never used in tests |
| `TEST_DATABASE_URL` | For live-DB tests | Must point to `ecops_test`, not `ecops` |
| `JWT_SECRET_KEY` | Yes | **Must be overridden** — default is insecure |
| `ANTHROPIC_API_KEY` | Yes (any string) | LM Studio ignores the value; set to `lmstudio` |
| `LMSTUDIO_BASE_URL` | For agent features | Default: `http://localhost:1234` |
| `LM_MODEL` | For agent features | Must match model identifier in LM Studio |
| `PORT` | No | Default: `8002` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default: `1440` (24 h) — reduce for production |
| `LOG_LEVEL` | No | `DEBUG` enables full LM Studio HTTP tracing |
