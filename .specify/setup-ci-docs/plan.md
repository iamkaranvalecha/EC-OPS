# Plan — setup-ci-docs

Stack: Python 3.12 · FastAPI · uv · pytest · ruff · Tailscale CI · PostgreSQL

This feature adds developer-experience tooling only — setup automation, request
collections, CI, and documentation. It does not touch order-domain logic, models,
or API behaviour. All paths follow repo conventions: scripts in `scripts/`,
request artifacts in `requests/`, docs in `docs/` and repo root, tests in `tests/`,
snake_case file naming.

## Phase 1 — Setup automation & request collection (setup-onboarding)
Milestone: setup-onboarding
Goal: One idempotent entrypoint script that checks prereqs, syncs deps, creates `.env`, sets up the DB, optionally starts the server, and prints next-step guidance; plus a generated Postman collection and a generator to keep it in sync with the `.http` files.
Spec requirements covered: R1.1, R1.2, R1.3, R1.4, R1.5
Success signals advanced: S1, S2
Tasks: T001, T002, T003, T004

## Phase 2 — CI via Tailscale (ci-tailscale)
Milestone: ci-tailscale
Goal: A GitHub Actions workflow that runs ruff and the test suite on every PR and push to main, connecting to the developer's local Postgres over Tailscale, with a documented `RUN_TESTS` opt-out and a setup guide.
Spec requirements covered: R2.1, R2.2, R2.3, R2.4, R2.5
Success signals advanced: S3, S4
Tasks: T005, T006

## Phase 3 — Design decisions document (design-docs)
Milestone: design-docs
Goal: A neutral `DESIGN_DECISIONS.md` covering each technical choice (decision, rationale, alternatives) and an anticipated-questions section, cross-linked from the README alongside the CI guide.
Spec requirements covered: R3.1, R3.2, R3.3, R3.4, R3.5
Success signals advanced: S5
Tasks: T007, T008
