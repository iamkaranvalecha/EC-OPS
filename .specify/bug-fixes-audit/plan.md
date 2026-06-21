# Plan — bug-fixes-audit

## Phases

### Phase 1 — Full audit (read-only)

Dispatch a deep-read agent to read all files under `src/`, `tests/`, and
`scripts/generate_insomnia.py` and produce the severity matrix.
Estimated scope: ~40 files.

Special attention areas identified up-front:
1. Any test that still references `DATABASE_URL` (the app DB) — past bug.
2. Race conditions in the A2A in-memory task store.
3. SSE `RunFinished` always-fires guarantee.
4. FastMCP 1.28 tuple result extraction.
5. Auth token query-param leakage in logs.
6. Guardrail regex correctness (`_TRACEBACK_RE`).
7. `_ReasoningFilter` unclosed `<think>` tag handling.
8. UUID parsing from LLM-provided strings (no ValueError guard).
9. Missing FK index on `order_items.order_id`.
10. `asyncio.create_task` return value discard in A2A.

### Phase 2 — Code fixes (in priority order)

Apply all code-level fixes in a single pass:

| Priority | File | Fix |
|---|---|---|
| CRITICAL/HIGH | `src/agent/a2a_router.py` | Store `asyncio.Task` handle; add `_task_handles` dict; clean up in `finally` |
| HIGH | `src/agent/tools.py` | Guard `UUID(order_id)` with `ValueError` in `get_order_tool` and `cancel_order_tool` |
| HIGH | `src/agent/executor.py` | Fallback message when `end_turn` produces no text block |
| MEDIUM | `src/agent/guardrails.py` | Fix `_TRACEBACK_RE` — change `.*` to `.*?(?=\n\n|\Z)` |
| MEDIUM | `src/agent/agui_stream.py` | Add `_ReasoningFilter.flush()`; call after `text_stream` loop; move tool-count check before `ToolCallStart`; replace `iteration` counter with `_iterations_run` |
| MEDIUM | `src/orders/exceptions.py` | Truncate UUID to 8 chars in `OrderNotFound` and `OrderNotCancellable` |
| LOW | `tests/orders/test_models.py` | `skipif` — remove `DATABASE_URL` as qualifying condition |
| LOW | `tests/orders/test_service.py` | Same `skipif` fix |

### Phase 3 — Verification

Run `uv run pytest tests/ -q` and confirm all 176 tests pass.

## Architectural findings (not fixed — require deployment decisions)

| Issue | Severity | Recommendation |
|---|---|---|
| `_tasks` in-memory dict in `a2a_router.py` — invisible across uvicorn workers | CRITICAL | Use Redis or a DB-backed task store for any multi-worker deployment |
| `run_migrations` tool exposed via MCP — callable by the LLM | HIGH | Remove from MCP server; expose only as a CLI management command |
| JWT query-param for SSE clients leaks token into server logs | MEDIUM | Document; implement short-lived SSE ticket exchange in a future iteration |
| `order_items.order_id` FK has no explicit index | MEDIUM | Add `index=True` in the mapped column; generate an Alembic migration |
| Default `JWT_SECRET_KEY` not validated at startup | HIGH | Add startup guard: raise if key equals the default literal string |
| `ACCESS_TOKEN_EXPIRE_MINUTES = 1440` with no revocation | LOW | Reduce to 60–120 min or add a JTI blocklist |
