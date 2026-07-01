# Spec — auth

## Verbatim request

> Add JWT Bearer authentication to the EC-OPS API. Every order endpoint and agent
> route should require a valid token. Auth endpoints (register, token) and the health
> check remain public. Users should be isolated — each user can only see their own orders.

## Background

EC-OPS had no authentication layer: any caller could read, create, cancel, or search
any order. Before exposing the agent to production traffic, all order-management
operations must be scoped to an authenticated user, and the agent's SSE/A2A endpoints
must be similarly protected.

## Requirements

### R1 — User model and migration
- R1.1 — A `users` table with columns: `id` (UUID PK), `username` (VARCHAR UNIQUE NOT NULL),
  `hashed_password` (VARCHAR NOT NULL), `is_active` (BOOLEAN DEFAULT TRUE), `created_at` (TIMESTAMPTZ).
- R1.2 — Alembic migration `0003_add_users_table.py` creates the table idempotently.
- R1.3 — `hashed_password` is never returned in any API response.

### R2 — User validation rules
- R2.1 — Username: 3–50 characters, alphanumeric plus hyphen/underscore only (`[a-zA-Z0-9_-]+`).
- R2.2 — Password: minimum 8 characters.
- R2.3 — Violations return 422 (FastAPI/Pydantic validation error).

### R3 — Registration endpoint
- R3.1 — `POST /auth/register` accepts `{ "username": ..., "password": ... }` and returns 201
  plus a `UserResponse` (id, username, is_active — no hashed_password).
- R3.2 — Duplicate username returns 409 with `detail` containing the username.
- R3.3 — Passwords are hashed with `bcrypt` before storage (`bcrypt.hashpw`). `passlib` is
  not used — it is incompatible with `bcrypt ≥ 5.0`.

### R4 — Login endpoint
- R4.1 — `POST /auth/token` uses `OAuth2PasswordRequestForm` (`application/x-www-form-urlencoded`,
  `username` + `password` fields) and returns `{ "access_token": "...", "token_type": "bearer" }`.
- R4.2 — Wrong password or unknown username returns 401.
- R4.3 — Login for a deactivated user (`is_active=False`) returns 401.
- R4.4 — Missing credentials return 422.

### R5 — JWT tokens (HS256)
- R5.1 — Tokens contain claims: `sub` (user UUID as string), `username`, `exp` (expiry).
- R5.2 — Signed with `JWT_SECRET_KEY` using HS256 algorithm (`python-jose[cryptography]`).
- R5.3 — Expiry controlled by `ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440 = 24 h).
- R5.4 — The default `JWT_SECRET_KEY` in `.env.example` must be overridden before exposing
  the server to any network.

### R6 — Authentication dependency
- R6.1 — `get_current_user` FastAPI dependency: extracts and validates the JWT, looks up
  the user, raises 401 if token is invalid, expired, or user is deactivated.
- R6.2 — Token is accepted from the `Authorization: Bearer <token>` header (primary) OR
  from a `?token=<jwt>` query parameter (fallback for browser `EventSource` clients, which
  cannot set custom headers). Header always takes precedence.
- R6.3 — `_resolve_token` is a sub-dependency that handles the header/query-param extraction.

### R7 — Route protection
- R7.1 — All five order routes (`POST /orders`, `GET /orders`, `GET /orders/{id}`,
  `PATCH /orders/{id}/status`, `DELETE /orders/{id}`) require `get_current_user`.
- R7.2 — All agent routes (`GET /agent/stream`, `POST /a2a/tasks/send`,
  `GET /a2a/tasks/{id}`, `GET /.well-known/agent.json`) require `get_current_user`.
- R7.3 — Public routes (no auth required): `GET /health`, `POST /auth/register`,
  `POST /auth/token`.
- R7.4 — Any request to a protected route without a valid token returns 401 (not 403).

### R8 — User-scoped order isolation
- R8.1 — `create_order` attaches `user_id` from the current user to the order row.
- R8.2 — `get_order`, `list_orders`, `cancel_order`, `update_order_status` filter by
  `user_id` — one user cannot see or modify another user's orders.
- R8.3 — Attempting to access another user's order by ID returns 404 (not 403) —
  the resource is treated as non-existent for that user.

### R9 — Initial user seed
- R9.1 — `scripts/seed_user.py` creates an initial admin account idempotently (re-running
  is safe). Username and password configurable via env vars or CLI args.
- R9.2 — The seed script is called by `scripts/setup.py` so first-time setup produces a
  usable account.

## Out of scope
- Token refresh / revocation (no `/auth/refresh` endpoint, no JTI blocklist).
- OAuth2 PKCE / third-party identity providers.
- Account management endpoints (change password, delete user, list users).
- Role-based access control.
