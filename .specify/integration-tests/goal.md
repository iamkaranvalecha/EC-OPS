# Feature Goal — integration-tests

## User goal
Every major HTTP contract in EC-OPS is verified end-to-end against a real PostgreSQL database:
auth flows, order lifecycle paths, status transitions, user isolation, and error responses —
all through the REST API with no DB shortcuts.

## Success signals
- [x] S1: `POST /auth/register` and `POST /auth/token` are tested end-to-end (201, 409, 422,
      401 cases) via `test_auth_api.py`.
- [x] S2: A complete register→login→create-order chain succeeds in a single test.
- [x] S3: Two users can register, create orders, and each sees only their own orders.
- [x] S4: An invalid token is rejected with 401 on all 5 protected order routes.
- [x] S5: An order walks the full lifecycle (PENDING→PROCESSING→SHIPPED→DELIVERED) via
      `PATCH /orders/{id}/status` calls only, verified at each step by `GET` and list-filter assertions.
- [x] S6: `DELETE /orders/{id}` on a PENDING order soft-deletes (204); record is retained with
      `status=CANCELLED`; terminal checks pass (409 on re-cancel, 422 on any PATCH).
- [x] S7: Cancel is rejected with 409 at PROCESSING, SHIPPED, and DELIVERED stages.
- [x] S8: A 3-item order's items, customer_name, and created_at are unchanged through all status
      transitions; updated_at progresses.
- [x] S9: Two orders advanced simultaneously on independent paths never contaminate each other's
      list-filter results.
- [x] S10: All 61 integration tests pass (61 tests across 4 files in tests/integration/) and
       all are auto-skipped when TEST_DATABASE_URL is absent.

## Spec coverage
S1  → spec req: R1.1–R1.11, R1.15–R1.17
S2  → spec req: R1.12
S3  → spec req: R1.13
S4  → spec req: R1.14
S5  → spec req: R2.1–R2.6
S6  → spec req: R2.7–R2.10
S7  → spec req: R2.11–R2.13
S8  → spec req: R2.14–R2.17
S9  → spec req: R2.18–R2.22
S10 → spec req: R3.2, R3.3

## Goal progress
All signals complete — feature shipped.
