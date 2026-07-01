# Feature Goal — auth

## User goal
A registered user logs in once, receives a JWT token, and uses it to access their
own orders and the AI agent. Other users' orders are invisible to them. Unauthenticated
callers are rejected with 401 on every protected route.

## Success signals
- [x] S1: `POST /auth/register` creates a new user (201) and never returns the hashed password.
- [x] S2: Duplicate username returns 409; invalid username/password format returns 422.
- [x] S3: `POST /auth/token` returns a Bearer JWT for valid credentials; wrong password or
      unknown user returns 401; deactivated user returns 401.
- [x] S4: Every order route (`POST`, `GET`, `GET list`, `PATCH`, `DELETE`) returns 401 without a token.
- [x] S5: Every agent route (`/agent/stream`, `/a2a/tasks/send`, `/a2a/tasks/{id}`,
      `/.well-known/agent.json`) returns 401 without a token.
- [x] S6: `GET /health`, `POST /auth/register`, `POST /auth/token` are accessible without a token.
- [x] S7: A token obtained via login can be used to create, read, list, and cancel orders.
- [x] S8: Two users who each create one order can each see only their own order via `GET /orders`.
- [x] S9: Attempting to GET or DELETE another user's order returns 404 (not 403).
- [x] S10: Browser SSE clients can pass the token via `?token=<jwt>` query parameter.

## Spec coverage
S1  → spec req: R3.1, R3.3
S2  → spec req: R2.1, R2.2, R2.3, R3.2
S3  → spec req: R4.1, R4.2, R4.3
S4  → spec req: R7.1
S5  → spec req: R7.2
S6  → spec req: R7.3
S7  → spec req: R6.1, R7.1
S8  → spec req: R8.1, R8.2
S9  → spec req: R8.3
S10 → spec req: R6.2

## Goal progress
All signals complete — feature shipped.
