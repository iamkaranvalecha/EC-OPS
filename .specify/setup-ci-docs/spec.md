# Spec — setup-ci-docs

Three developer-experience features for the EC-OPS solution. None of these
touch application/order-domain logic; they add tooling, automation, and docs.

## Verbatim request

> I want to develop three features in this solution.
> 1. a script to setup and run this solution and guide user to what to do next
>    and how to fire requests using .http files or create a postman collection
>    using .http files and save it in repo for user to use.
> 2. CI/CD integration of test suite. every PR should run test cases with
>    configuration available to make it optional.
> 3. A design decision document as to why certain tool was used or all the
>    questions an [reviewer] can ask about this [project] without mentioning
>    anything about [reviewer or author or assignment].

## Feature 1 — Setup & run script with onboarding guidance

A single entrypoint script that sets the solution up, runs it, and tells the
user exactly what to do next.

Requirements:
- R1.1 — One cross-platform-friendly script (e.g. `scripts/setup.py` invoked via
  `uv run`, plus optional thin `setup.sh`/`setup.ps1` wrappers) that: checks
  prerequisites (Python 3.12+, uv, PostgreSQL reachable), runs `uv sync --extra
  dev`, copies `.env.example` → `.env` if missing, runs the existing
  `scripts/db_setup.py`, and can start the server.
- R1.2 — On completion the script prints a clear "what to do next" guide:
  the local URL, how to run the REST endpoints, and how to use the AI agent.
- R1.3 — Guidance on firing requests two ways: (a) the existing `.http` files in
  `requests/` (VS Code REST Client / JetBrains HTTP Client), and (b) a Postman
  collection.
- R1.4 — Generate a Postman v2.1 collection from the existing `.http` files and
  save it into the repo (e.g. `requests/EC-OPS.postman_collection.json`) with a
  `baseUrl` variable, so users can import and run it. Provide a small generator
  so the collection can be regenerated when `.http` files change.
- R1.5 — The script must verify actual state (files exist, commands present) and
  fail with a clear message rather than guessing. It must be idempotent — safe
  to run more than once.

## Feature 2 — CI/CD test suite integration

Run the test suite automatically on every pull request, with a switch to make
it optional.

Requirements:
- R2.1 — A GitHub Actions workflow (`.github/workflows/ci.yml`) triggered on
  `pull_request` (and pushes to `main`) that installs uv, runs `uv sync --extra
  dev`, runs `ruff check`, and runs the test suite.
- R2.2 — The CI runner connects to the developer's **local PostgreSQL instance via
  Tailscale** (no in-CI database service container). The workflow must:
  (a) install and authenticate the Tailscale GitHub Action using a Tailscale
      auth key stored as a GitHub Actions secret (`TAILSCALE_AUTHKEY`);
  (b) wait until the Tailscale node (the developer's machine) is reachable before
      running tests;
  (c) set `DATABASE_URL` and `TEST_DATABASE_URL` from GitHub Actions secrets
      (`DB_URL` / `TEST_DB_URL`) that encode the Tailscale IP/hostname of the
      local machine and the existing `ecops` / `ecops_test` databases.
  The workflow must NOT spin up any Postgres container — it relies entirely on the
  local database.
- R2.3 — Make the test run optional/configurable: a documented mechanism (e.g. a
  repo/workflow variable like `RUN_TESTS`, and/or a `[skip ci]`/label gate) that
  lets a maintainer skip the test job without editing the workflow. Default is
  ON (tests run).
- R2.4 — The workflow must surface pass/fail clearly as a PR status check.
- R2.5 — Document the CI behaviour, the Tailscale setup steps (auth key secret,
  machine reachability, required GitHub secrets), and the opt-out switch in the
  README (and in a `docs/ci-tailscale.md` guide).

## Feature 3 — Design decisions document

A document explaining the technical choices made in the solution, framed as a
neutral engineering rationale plus an anticipated-questions section.

Requirements:
- R3.1 — A `DESIGN_DECISIONS.md` (or `docs/DESIGN_DECISIONS.md`) covering why the
  key tools/choices were made: FastAPI, PostgreSQL + pgvector, SQLAlchemy async +
  asyncpg, Alembic, APScheduler, MCP, A2A, AG-UI/SSE, uv, pytest, ruff, and the
  LM Studio Anthropic-compatible endpoint.
- R3.2 — For each choice: the decision, the rationale, and alternatives
  considered / trade-offs.
- R3.3 — An "anticipated questions" section: the questions a technical reviewer
  could reasonably ask about this project, each with a concise answer. Topics:
  architecture, data model, concurrency/async, the scheduler & order lifecycle,
  validation, testing strategy, the agent/protocol layer, scaling, and security.
- R3.4 — Strictly neutral framing. The document must NOT mention an interviewer,
  interviewee, candidate, hiring, or a "home assignment" — it reads as ordinary
  project engineering documentation.
- R3.5 — Cross-link from the README so the document is discoverable.

## Out of scope
- No changes to order-domain logic, models, or API behaviour.
- No cloud deployment; CI runs tests only (no deploy/CD step).
- No auth.
