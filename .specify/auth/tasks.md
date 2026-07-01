# Tasks — auth

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — User model and migration
- **Status**: [x]
- **Phase**: 1 — Data layer
- **Milestone**: auth-mvp
- **Spec requirement**: R1
- **Goal signals**: S1
- **Scope**: src/auth/__init__.py, src/auth/models.py, migrations/versions/0003_add_users_table.py
- **Done when**:
  - `User` SQLAlchemy model: `id` (UUID PK, uuid4 default), `username` (VARCHAR unique NOT NULL),
    `hashed_password` (VARCHAR NOT NULL), `is_active` (BOOLEAN default True), `created_at`
    (TIMESTAMPTZ, server_default=func.now()).
  - `orders.user_id` FK column added to `Order` model (UUID, FK → users.id, nullable for migration
    backwards-compat, then required going forward).
  - Migration `0003_add_users_table.py` creates the `users` table and adds `user_id` to `orders`;
    `uv run alembic upgrade head` is idempotent.
- **Brief**: Additive migration — existing orders get `user_id=NULL` after migration, which is
  cleaned up by the seed + auth enforcement in T005/T006. No destructive schema changes.

## T002 — Auth schemas and service layer
- **Status**: [x]
- **Phase**: 1 — Data layer
- **Milestone**: auth-mvp
- **Spec requirement**: R2, R3.3, R5.1
- **Goal signals**: S1, S2, S3
- **Scope**: src/auth/schemas.py, src/auth/service.py
- **Done when**:
  - `UserCreate`: `username` (str, min_length=3, pattern `^[a-zA-Z0-9_-]+$`),
    `password` (str, min_length=8). Both violate → 422 from FastAPI.
  - `UserResponse`: `id`, `username`, `is_active` — NO `hashed_password` field.
  - `TokenResponse`: `access_token` (str), `token_type` (literal "bearer").
  - `create_user(data: UserCreate, session) → User` — hashes password with `bcrypt.hashpw`,
    inserts user, returns model.
  - `get_user_by_username(username, session) → User | None`.
  - `authenticate_user(username, password, session) → User | None` — returns None for wrong
    password, unknown user, or inactive user.
  - `create_access_token(user_id, username) → str` — signs with HS256, embeds `sub`, `username`,
    `exp` claims. No `passlib` dependency.
  - `ruff check src/auth/` passes.

## T003 — Auth router (`/auth/register` and `/auth/token`)
- **Status**: [x]
- **Phase**: 2 — Auth endpoints + JWT
- **Milestone**: auth-mvp
- **Spec requirement**: R3, R4
- **Goal signals**: S1, S2, S3
- **Scope**: src/auth/router.py, src/main.py
- **Done when**:
  - `POST /auth/register`: 201 + `UserResponse`; 409 with `detail` containing username on duplicate.
  - `POST /auth/token`: `OAuth2PasswordRequestForm` (`application/x-www-form-urlencoded`);
    200 + `TokenResponse` on success; 401 on wrong password / unknown user / inactive user;
    422 on missing fields.
  - Both routes mounted under `/auth` prefix in `src/main.py`.
  - `uv run pytest tests/auth/test_auth_router.py -k "test_register or test_login"` passes.

## T004 — JWT dependency: `get_current_user` + dual token extraction
- **Status**: [x]
- **Phase**: 2 — Auth endpoints + JWT
- **Milestone**: auth-mvp
- **Spec requirement**: R5, R6
- **Goal signals**: S4, S5, S6, S10
- **Scope**: src/auth/dependencies.py
- **Done when**:
  - `_resolve_token(authorization: str | None = Header(None), token: str | None = Query(None))
    → str | None` — returns the header Bearer token first; falls back to `?token=` query param;
    returns None if neither is present.
  - `get_current_user(token: str | None = Depends(_resolve_token), session = Depends(get_session))
    → User` — decodes JWT (python-jose), validates `exp` and `sub`, loads user from DB,
    raises `HTTPException(401)` for invalid token, expired token, or `is_active=False`.
  - A garbage JWT string raises 401, not 500.
  - `uv run pytest tests/auth/ -k "test_protected or test_token or test_deactivated"` passes.

## T005 — Protect all order and agent routes
- **Status**: [x]
- **Phase**: 3 — Route protection + user scoping
- **Milestone**: auth-mvp
- **Spec requirement**: R7
- **Goal signals**: S4, S5, S6
- **Scope**: src/orders/router.py, src/agent/agui_stream.py, src/agent/a2a_router.py
- **Done when**:
  - All five order route handlers have `current_user: User = Depends(get_current_user)` in
    their signatures.
  - `/agent/stream`, `/a2a/tasks/send`, `/a2a/tasks/{id}`, `/.well-known/agent.json` all
    include the same dependency.
  - `GET /health`, `POST /auth/register`, `POST /auth/token` have NO auth dependency.
  - `uv run pytest tests/auth/test_agent_route_auth.py` passes (12 tests verifying 401 on all
    agent/A2A routes + 5 `_resolve_token` unit tests).

## T006 — User-scoped order queries
- **Status**: [x]
- **Phase**: 3 — Route protection + user scoping
- **Milestone**: auth-mvp
- **Spec requirement**: R8
- **Goal signals**: S7, S8, S9
- **Scope**: src/orders/service.py
- **Done when**:
  - `create_order` accepts `user_id: UUID` kwarg and stores it on the order row.
  - `get_order(order_id, session, user_id=None)` adds `WHERE user_id = :user_id` when
    `user_id` is supplied; returns None (→ 404) if the row belongs to a different user.
  - `list_orders(session, status=None, user_id=None)` filters by `user_id` when supplied.
  - `cancel_order` and `update_order_status` pass `user_id` down to `get_order` so
    cross-user access returns OrderNotFound.
  - Integration test: two users each create one order; `GET /orders` for user A returns
    only user A's order; accessing user B's order ID as user A returns 404.

## T007 — `scripts/seed_user.py`
- **Status**: [x]
- **Phase**: 4 — Seed + tests
- **Milestone**: auth-mvp
- **Spec requirement**: R9
- **Goal signals**: S7
- **Scope**: scripts/seed_user.py, scripts/setup.py
- **Done when**:
  - `uv run python scripts/seed_user.py` creates (or skips if already exists) an admin account.
  - Username/password configurable via `SEED_USERNAME` / `SEED_PASSWORD` env vars or CLI args.
  - Idempotent: running twice leaves exactly one user with the given username.
  - `scripts/setup.py` calls `seed_user.py` after migrations.

## T008 — Auth unit + integration tests
- **Status**: [x]
- **Phase**: 4 — Seed + tests
- **Milestone**: auth-mvp
- **Spec requirement**: R2, R3, R4, R6, R7, R8
- **Goal signals**: S1–S10
- **Scope**: tests/auth/test_auth_router.py, tests/auth/test_auth_service.py, tests/auth/test_agent_route_auth.py, tests/integration/test_auth_api.py
- **Done when**:
  - `tests/auth/test_auth_router.py`: register success, duplicate 409, short password 422,
    username too short/special-chars 422, login success, wrong password 401, nonexistent user 401,
    garbage token 401, health public, deactivated user 401 (via DB direct update).
  - `tests/auth/test_agent_route_auth.py`: 7 tests asserting 401 on all agent/A2A routes without
    auth; 5 unit tests for `_resolve_token` (header, query param, both, neither, header takes priority).
  - `tests/integration/test_auth_api.py`: 18 full-stack tests (register success/duplicate/validation,
    login happy/error paths, E2E register→token→create-order, two-user isolation, invalid token on
    all 5 order routes, public endpoint checks).
  - `uv run pytest tests/auth/ tests/integration/test_auth_api.py` passes.
