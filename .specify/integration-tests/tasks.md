# Tasks — integration-tests

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — Auth integration tests (`tests/integration/test_auth_api.py`)
- **Status**: [x]
- **Phase**: 1 — Auth integration tests
- **Milestone**: integration-tests
- **Spec requirement**: R1, R3
- **Goal signals**: S1, S2, S3, S4
- **Scope**: tests/integration/test_auth_api.py
- **Done when**:
  - File exists at `tests/integration/test_auth_api.py`.
  - Uses `raw_client: AsyncClient` fixture from `tests/conftest.py` (pre-authenticated per-test
    user is NOT used here — these tests are specifically testing the unauthenticated auth flows).
  - 18 passing tests:

    *Registration (7 tests):*
    - `test_register_returns_201_with_user_object` — body: username, is_active=True, id; no hashed_password.
    - `test_register_duplicate_username_returns_409` — detail contains the username.
    - `test_register_short_password_returns_422`
    - `test_register_username_too_short_returns_422`
    - `test_register_username_with_special_chars_returns_422`
    - `test_register_missing_username_returns_422`
    - `test_register_missing_password_returns_422`

    *Login (4 tests):*
    - `test_login_returns_bearer_token` — token_type="bearer", len(access_token) > 20.
    - `test_login_wrong_password_returns_401`
    - `test_login_unknown_user_returns_401`
    - `test_login_missing_credentials_returns_422`

    *End-to-end (3 tests):*
    - `test_register_login_then_create_order` — register, token, POST /orders with token → 201,
      body.customer_name correct, body.status="PENDING".
    - `test_token_isolates_orders_between_users` — User A and B each register + create 1 order;
      GET /orders as A returns exactly 1 order (A's); same for B.
    - `test_invalid_token_rejected_on_every_orders_route` — "Bearer this.is.not.valid" returns
      401 on GET /orders, POST /orders, GET /orders/{uuid}, PATCH /orders/{uuid}/status,
      DELETE /orders/{uuid}.

    *Public endpoint checks (3 tests):*
    - `test_health_endpoint_is_public` — GET /health → 200, body.status == "ok".
    - `test_auth_register_is_public` — POST /auth/register → 201 (no auth header needed).
    - `test_auth_token_is_public` — POST /auth/token → 200 (no auth header needed).

  - `uv run pytest tests/integration/test_auth_api.py` passes (auto-skipped when TEST_DATABASE_URL absent).
- **Brief**: Purely HTTP-level; no db_session direct writes. Each test registers a fresh username
  with a uuid suffix to avoid duplicate conflicts across test runs without relying on TRUNCATE timing.

## T002 — Order lifecycle tests (`tests/integration/test_order_lifecycle.py`)
- **Status**: [x]
- **Phase**: 2 — Order lifecycle tests
- **Milestone**: integration-tests
- **Spec requirement**: R2, R3
- **Goal signals**: S5, S6, S7, S8, S9
- **Scope**: tests/integration/test_order_lifecycle.py
- **Done when**:
  - File exists at `tests/integration/test_order_lifecycle.py`.
  - Uses `api_client: AsyncClient` fixture (pre-authenticated user).
  - Defines shared helper functions at module level:
    ```python
    async def _create(client, payload) → str      # asserts 201, returns id
    async def _get(client, order_id) → dict       # asserts 200
    async def _patch_status(client, order_id, status) → dict  # asserts 200 + body.status == status
    async def _list_by_status(client, status) → list[dict]    # asserts 200
    async def _cancel(client, order_id) → None    # asserts 204
    ```
  - 5 passing lifecycle tests:

    **Variant 1 — `test_lifecycle_full_fulfilment`:**
    - Creates single-item order; asserts status=PENDING, updated_at=None.
    - Appears in PENDING list. PATCH to PROCESSING: GET + list-filter assertions.
    - PATCH to SHIPPED: same. PATCH to DELIVERED: same.
    - Terminal: PATCH to SHIPPED → 422; PATCH to PENDING → 422; DELETE → 409.
    - Order still retrievable as DELIVERED.

    **Variant 2 — `test_lifecycle_early_cancel`:**
    - Creates order; asserts PENDING in list.
    - DELETE → 204. GET: status=CANCELLED, updated_at not None.
    - Appears in CANCELLED list; absent from PENDING list.
    - Terminal: DELETE again → 409; PATCH to PROCESSING/SHIPPED/DELIVERED → 422.

    **Variant 3 — `test_lifecycle_cancel_blocked_after_processing`:**
    - Creates order, PATCH to PROCESSING. DELETE → 409. GET confirms still PROCESSING.
    - PATCH to SHIPPED. DELETE → 409. GET confirms still SHIPPED.
    - PATCH to DELIVERED. DELETE → 409. GET confirms still DELIVERED.

    **Variant 4 — `test_lifecycle_multi_item_items_survive_transitions`:**
    - Creates 3-item order (Laptop/Mouse/Keyboard). Asserts 3 items, correct names/quantities/prices.
    - Captures created_at. PATCH to PROCESSING: response body has 3 items, same created_at, not-None updated_at.
    - PATCH to SHIPPED: same invariants. PATCH to DELIVERED: same.
    - Final GET: status=DELIVERED, 3 items, customer_name unchanged.

    **Variant 5 — `test_lifecycle_two_orders_independent_paths`:**
    - Creates Order A and Order B. Both appear in PENDING list.
    - PATCH A to PROCESSING; DELETE B. Neither in PENDING list.
    - A in PROCESSING list; B in CANCELLED list.
    - PATCH B to PROCESSING → 422 (terminal).
    - PATCH A to SHIPPED then DELIVERED. A in DELIVERED list, B still in CANCELLED.
    - Final: GET A → DELIVERED, GET B → CANCELLED. Both terminal: PATCH A → 422, DELETE A → 409, DELETE B → 409.

  - `uv run pytest tests/integration/test_order_lifecycle.py` passes (5 tests collected; auto-skipped when TEST_DATABASE_URL absent).
- **Brief**: No `_force_status`, no `db_session` manipulation — every state change goes through
  the HTTP API, validating the full request/response contract at each step.
