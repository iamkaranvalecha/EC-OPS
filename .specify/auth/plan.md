# Implementation Plan — auth

Stack: Python 3.12 + FastAPI + SQLAlchemy async + asyncpg | JWT: python-jose[cryptography] + bcrypt | uv | ruff

## Phase 1 — Data layer
Milestone: auth-mvp
Goal: `users` table migrated, User ORM model in place, password hashing utility working.
Spec requirements covered: R1, R2, R3.3
Tasks: T001, T002

## Phase 2 — Auth endpoints + JWT
Milestone: auth-mvp
Goal: `POST /auth/register` and `POST /auth/token` working end-to-end; JWT tokens issued and
verifiable; `get_current_user` dependency implemented with header + query-param fallback.
Spec requirements covered: R3, R4, R5, R6
Tasks: T003, T004

## Phase 3 — Route protection + user scoping
Milestone: auth-mvp
Goal: All order and agent routes require a valid token; order queries scoped to user_id;
cross-user isolation verified.
Spec requirements covered: R7, R8
Tasks: T005, T006

## Phase 4 — Seed script + tests
Milestone: auth-mvp
Goal: Initial user seed integrated into setup; full unit and integration test coverage.
Spec requirements covered: R9
Tasks: T007, T008

---

## Phase 1 — Data layer

### T001 — User model and migration
- Spec req: R1 · Signals: S1
- Scope: src/auth/models.py, migrations/versions/0003_add_users_table.py
- Done when: `User` ORM model with id (UUID PK), username (unique), hashed_password, is_active, created_at; migration `0003_add_users_table` creates the table; `alembic upgrade head` is idempotent.

### T002 — Auth schemas and service
- Spec req: R2, R3.3 · Signals: S1, S2, S3
- Scope: src/auth/schemas.py, src/auth/service.py
- Done when: `UserCreate` (username: min 3, regex `[a-zA-Z0-9_-]+`; password: min 8), `UserResponse` (no hashed_password), `TokenResponse`; `create_user`, `get_user_by_username`, `authenticate_user`, `create_access_token` service functions; bcrypt hashing via `bcrypt.hashpw`/`bcrypt.checkpw` (no passlib).

## Phase 2 — Auth endpoints + JWT

### T003 — Auth router (register + token)
- Spec req: R3, R4, R5 · Signals: S1, S2, S3
- Scope: src/auth/router.py, src/main.py
- Done when: `POST /auth/register` → 201 or 409; `POST /auth/token` (OAuth2PasswordRequestForm) → bearer token or 401; both wired into the FastAPI app under `/auth` prefix.

### T004 — get_current_user dependency + dual token extraction
- Spec req: R5, R6 · Signals: S4, S5, S6, S10
- Scope: src/auth/dependencies.py, src/core/dependencies.py
- Done when: `_resolve_token` checks Authorization header first, falls back to `?token=` query param; `get_current_user` decodes JWT, validates claims, checks `is_active`; invalid/expired token or deactivated user raises 401.

## Phase 3 — Route protection + user scoping

### T005 — Protect all order and agent routes
- Spec req: R7 · Signals: S4, S5, S6
- Scope: src/orders/router.py, src/agent/agui_stream.py, src/agent/a2a_router.py
- Done when: all five order routes and all agent routes include `get_current_user = Depends(get_current_user)` in their signatures; `/health`, `/auth/register`, `/auth/token` have no auth dep.

### T006 — User-scoped order queries
- Spec req: R8 · Signals: S7, S8, S9
- Scope: src/orders/service.py, src/orders/models.py
- Done when: `orders.user_id` FK column added; `create_order` sets `user_id`; `get_order`, `list_orders`, `cancel_order`, `update_order_status` filter by `user_id`; cross-user access returns 404.

## Phase 4 — Seed script + tests

### T007 — scripts/seed_user.py
- Spec req: R9 · Signals: S7
- Scope: scripts/seed_user.py, scripts/setup.py
- Done when: seed_user.py creates/updates the initial admin account idempotently; called from setup.py.

### T008 — Unit and integration tests
- Spec req: R2, R3, R4, R6, R7, R8 · Signals: S1–S10
- Scope: tests/auth/test_auth_router.py, tests/auth/test_auth_service.py, tests/auth/test_agent_route_auth.py
- Done when: all auth flows covered (happy paths, 409/422/401 error cases, deactivated user, cross-user isolation, SSE ?token= path); `uv run pytest tests/auth/` passes.
