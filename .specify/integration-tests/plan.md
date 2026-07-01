# Implementation Plan — integration-tests

Stack: Python 3.12 + pytest + pytest-asyncio + httpx | PostgreSQL (test DB: ecops_test) | Auto-skip when TEST_DATABASE_URL absent

## Phase 1 — Auth integration tests
Milestone: integration-tests
Goal: All 17 auth HTTP contract cases passing against a real database.
Spec requirements covered: R1, R3
Tasks: T001

## Phase 2 — Order lifecycle integration tests
Milestone: integration-tests
Goal: 5 lifecycle variant tests walk complete order paths using only REST API calls.
Spec requirements covered: R2, R3
Tasks: T002

---

## Phase 1 — Auth integration tests

### T001 — tests/integration/test_auth_api.py (18 tests)
- Spec req: R1, R3 · Signals: S1, S2, S3, S4
- Scope: tests/integration/test_auth_api.py
- Done when: 18 tests pass:
  - Register: 201 + body shape, 409 duplicate, 422 short password, 422 short username, 422 special-char username, 422 missing username, 422 missing password.
  - Login: 200 + bearer token, 401 wrong password, 401 unknown user, 422 missing credentials.
  - E2E: register→login→create-order succeeds.
  - Two-user isolation: each user sees only their own order in GET /orders.
  - Invalid token: 401 on GET/POST /orders, GET /orders/{id}, PATCH /orders/{id}/status, DELETE /orders/{id}.
  - Public: /health 200, /auth/register 201, /auth/token 200 — all without auth.

## Phase 2 — Order lifecycle tests

### T002 — tests/integration/test_order_lifecycle.py (5 variants)
- Spec req: R2, R3 · Signals: S5, S6, S7, S8, S9
- Scope: tests/integration/test_order_lifecycle.py
- Done when: 5 lifecycle variant tests pass using the helper functions `_create`, `_get`,
  `_patch_status`, `_list_by_status`, `_cancel` — all of which assert the correct HTTP
  status code on every call:
  1. Full fulfilment: PENDING→PROCESSING→SHIPPED→DELIVERED, list filters at each stage, terminal 422/409.
  2. Early cancel: PENDING→CANCELLED, soft-delete verified, terminal 409 re-cancel, 422 any PATCH.
  3. Cancel blocked: 409 at PROCESSING, SHIPPED, DELIVERED stages; order status unchanged after attempt.
  4. Multi-item: 3-item order, items + customer_name + created_at unchanged through all transitions.
  5. Parallel orders: A→DELIVERED, B→CANCELLED simultaneously; list filters always correct.
