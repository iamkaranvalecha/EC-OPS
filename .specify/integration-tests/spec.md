# Spec — integration-tests

## Verbatim request

> is there any integration test case available which tests order's lifecycle from start to end?

> yes.. everything should be done via api.. create few variants too

> verify other apis again with same process.. APIs are priority.. everything should work

## Background

EC-OPS already had integration tests in `tests/integration/test_orders_api.py` covering the
basic order CRUD flow. Two gaps remained:

1. **Auth integration coverage** — The auth feature (`/auth/register`, `/auth/token`, user isolation,
   invalid token rejection) had unit tests but no integration tests verifying the full HTTP stack
   against a real database.

2. **Lifecycle coverage** — No test walked an order from creation through every status to a terminal
   state using only REST API calls. Existing tests either stopped at one transition or used direct DB
   writes (`db_session.execute(update(...))`) rather than the API, leaving the HTTP contract
   unverified end-to-end.

This feature fills both gaps with purely HTTP-level tests — no DB shortcuts, no `_force_status`
helpers, no dependency overrides.

## Philosophy: API-only integration tests

All tests in `tests/integration/` must:
- Use only `httpx.AsyncClient` calls against the running FastAPI app.
- Assert the correct HTTP status code on every call before proceeding.
- Never write to the database directly (no `db_session.execute(update(...))`).
- Never import internal service functions or bypass the authentication layer.
- Be auto-skipped when `TEST_DATABASE_URL` is not set.

This approach validates the full request/response contract — auth, routing, validation,
business logic, DB persistence, and response serialisation — in one shot.

## Requirements

### R1 — Auth integration tests (`tests/integration/test_auth_api.py`)

**Registration:**
- R1.1 — `POST /auth/register` with valid credentials → 201, body contains `username`, `is_active=True`,
  `id`; does NOT contain `hashed_password`.
- R1.2 — Duplicate username → 409, detail contains the username.
- R1.3 — Password < 8 chars → 422.
- R1.4 — Username < 3 chars → 422.
- R1.5 — Username with special characters (e.g. `@`) → 422.
- R1.6 — Missing `username` field → 422.
- R1.7 — Missing `password` field → 422.

**Login:**
- R1.8 — `POST /auth/token` with valid credentials → 200, `token_type="bearer"`, `access_token` length > 20.
- R1.9 — Wrong password → 401.
- R1.10 — Unknown username → 401.
- R1.11 — Missing both credentials → 422.

**End-to-end:**
- R1.12 — Register → login → create order: the full chain succeeds; created order has correct
  `customer_name` and `status="PENDING"`.
- R1.13 — Two-user isolation: User A and User B each register, each create one order; `GET /orders`
  as User A returns exactly one order (User A's); same for User B.
- R1.14 — Invalid token on every protected order route: `GET /orders`, `POST /orders`, `GET /orders/{id}`,
  `PATCH /orders/{id}/status`, `DELETE /orders/{id}` all return 401.

**Public endpoints:**
- R1.15 — `GET /health` → 200, no auth required.
- R1.16 — `POST /auth/register` → 201, no auth required (it is how you get a user).
- R1.17 — `POST /auth/token` → 200, no auth required (it is how you get a token).

Total: 18 tests.

### R2 — Lifecycle integration tests (`tests/integration/test_order_lifecycle.py`)

Five variants, each using only REST API calls with reusable helpers:

```python
async def _create(client, payload) → str           # asserts 201, returns order id
async def _get(client, order_id) → dict            # asserts 200
async def _patch_status(client, order_id, status) → dict  # asserts 200, asserts body.status == status
async def _list_by_status(client, status) → list[dict]    # asserts 200
async def _cancel(client, order_id) → None         # asserts 204
```

**Variant 1 — Full fulfilment (PENDING → PROCESSING → SHIPPED → DELIVERED):**
- R2.1 — Created order has `status="PENDING"`, `updated_at=None`.
- R2.2 — Appears in `GET /orders?status=PENDING` list.
- R2.3 — Each PATCH advances the status and sets `updated_at`.
- R2.4 — List filters are correct at every stage: order appears in the new status bucket and
  disappears from the old one.
- R2.5 — Terminal checks: PATCH to any status on a DELIVERED order → 422; DELETE → 409.
- R2.6 — Order remains retrievable after DELIVERED.

**Variant 2 — Early cancel (PENDING → CANCELLED):**
- R2.7 — `DELETE /orders/{id}` on a PENDING order → 204.
- R2.8 — `GET /orders/{id}` after cancel → 200, `status="CANCELLED"`, `updated_at` is not None.
- R2.9 — Order appears in `GET /orders?status=CANCELLED`; absent from PENDING list.
- R2.10 — Terminal checks: second DELETE → 409; any PATCH → 422.

**Variant 3 — Cancel blocked after processing:**
- R2.11 — DELETE on a PROCESSING order → 409; order remains PROCESSING.
- R2.12 — DELETE on a SHIPPED order → 409; order remains SHIPPED.
- R2.13 — DELETE on a DELIVERED order → 409; order remains DELIVERED.

**Variant 4 — Multi-item order, items survive transitions:**
- R2.14 — Order created with 3 distinct items (Laptop, Mouse, Keyboard).
- R2.15 — `items`, `customer_name`, and `created_at` are identical on `GET` at every stage.
- R2.16 — `updated_at` is not None after the first PATCH and is non-decreasing.
- R2.17 — PATCH response body includes `items` (len 3) at every stage.

**Variant 5 — Two parallel orders, independent paths:**
- R2.18 — Order A and Order B both start PENDING; both appear in the PENDING list.
- R2.19 — Advance A to PROCESSING; cancel B: neither appears in PENDING list; A is in PROCESSING,
  B is in CANCELLED.
- R2.20 — B is terminal: PATCH to PROCESSING → 422.
- R2.21 — Advance A to DELIVERED: A appears in DELIVERED, B still in CANCELLED.
- R2.22 — Both are terminal: A → PATCH 422, A → DELETE 409, B → DELETE 409.

Total: 5 tests.

### R3 — Test infrastructure
- R3.1 — All tests use a `raw_client: AsyncClient` fixture pre-authenticated with a unique per-test
  user (registered and logged in during fixture setup), OR use `api_client` for lifecycle tests where
  a single long-lived session makes sense.
- R3.2 — Tests are auto-skipped when `TEST_DATABASE_URL` is absent (`pytest.mark.skipif` or
  conftest autouse guard).
- R3.3 — `TRUNCATE ... CASCADE` between tests ensures isolation.
- R3.4 — No `@pytest.mark.asyncio` decorators needed — `asyncio_mode = "auto"` in `pyproject.toml`.

## Out of scope
- Tests that require LM Studio (marked `@pytest.mark.slow`, none written here).
- Performance or load tests.
- Tests for the chat frontend (browser automation).
