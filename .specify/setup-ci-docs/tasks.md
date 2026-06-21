# Tasks

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — Setup & run script (scripts/setup.py)
- **Status**: [x]
- **Phase**: Setup automation & request collection
- **Milestone**: setup-onboarding
- **Spec requirement**: R1.1, R1.5
- **Goal signals**: S1
- **Scope**: scripts/setup.py
- **Done when**:
  - `scripts/setup.py` exists and runs via `uv run python scripts/setup.py --help` with exit code 0.
  - Checks prerequisites: Python >= 3.12, `uv` on PATH, and PostgreSQL reachable using the `DATABASE_URL` host/port; each missing prereq prints a clear, specific error and exits non-zero.
  - Runs `uv sync --extra dev`; copies `.env.example` -> `.env` only if `.env` is missing (never overwrites); runs `scripts/db_setup.py`.
  - Supports an opt-in flag (e.g. `--start` / `--run`) to launch the server via `python -m src.main`; without it, setup completes without starting the server.
  - Idempotent: a second consecutive run completes with exit code 0 and does not clobber an existing `.env`.
  - `ruff check scripts/setup.py` passes.
- **Brief**: Single Python entrypoint invoked through `uv`. Reuse the existing `scripts/db_setup.py` and `.env.example`. Read the DB host/port from `DATABASE_URL` to test Postgres reachability (a socket connect is sufficient). Verify actual state before each action and fail loudly with actionable messages rather than guessing. Server start runs `python -m src.main` (port 8002).

## T002 — Onboarding "what to do next" guidance in setup script
- **Status**: [x]
- **Phase**: Setup automation & request collection
- **Milestone**: setup-onboarding
- **Spec requirement**: R1.2, R1.3
- **Goal signals**: S1
- **Scope**: scripts/setup.py
- **Done when**:
  - On successful completion `scripts/setup.py` prints the local base URL (`http://localhost:8002`), how to call the REST endpoints, and how to use the AI agent (`/agent/stream`).
  - The printed guidance describes both request paths: (a) the existing `.http` files in `requests/` (VS Code REST Client / JetBrains HTTP Client) and (b) importing `requests/EC-OPS.postman_collection.json` into Postman and setting `baseUrl`.
  - Guidance text is verifiable by running the script and asserting the URL and both request methods appear in stdout.
  - `ruff check scripts/setup.py` passes.
- **Brief**: Extend the T001 script with a final summary block. Keep it accurate to the real endpoints in `requests/*.http` (orders REST, agent SSE stream, A2A). Reference the Postman collection produced in T003/T004 by its repo path.

## T003 — Postman collection generator (scripts/generate_postman.py)
- **Status**: [x]
- **Phase**: Setup automation & request collection
- **Milestone**: setup-onboarding
- **Spec requirement**: R1.4
- **Goal signals**: S2
- **Scope**: scripts/generate_postman.py, tests/scripts/test_generate_postman.py
- **Done when**:
  - `scripts/generate_postman.py` exists and runs via `uv run python scripts/generate_postman.py` with exit code 0, reading every `.http` file in `requests/` and writing `requests/EC-OPS.postman_collection.json`.
  - `tests/scripts/test_generate_postman.py` asserts the generator parses `.http` request lines (method + URL), groups requests by source file, substitutes `@baseUrl` with a `{{baseUrl}}` collection variable, and includes request bodies/headers where present.
  - `uv run pytest tests/scripts/test_generate_postman.py` passes.
  - `ruff check scripts/generate_postman.py tests/scripts/test_generate_postman.py` passes.
- **Brief**: Pure-logic parser converting VS Code REST Client `.http` syntax (`###` separators, `@var` definitions, `METHOD URL`, headers, JSON bodies) into Postman Collection v2.1 items. Replace the hardcoded `http://localhost:8002` / `@baseUrl` with a `{{baseUrl}}` variable. Unit-test the parser against a small fixture; this is the one task in the feature with enough logic to warrant a test file.

## T004 — Generate and commit the Postman v2.1 collection
- **Status**: [x]
- **Phase**: Setup automation & request collection
- **Milestone**: setup-onboarding
- **Spec requirement**: R1.4
- **Goal signals**: S2
- **Scope**: requests/EC-OPS.postman_collection.json
- **Done when**:
  - `requests/EC-OPS.postman_collection.json` exists and is valid JSON conforming to Postman Collection schema v2.1.0 (`info.schema` references `v2.1.0`).
  - The collection defines a `baseUrl` variable defaulting to `http://localhost:8002` and every request URL uses `{{baseUrl}}`.
  - The collection contains items for the requests in `requests/agent.http`, `requests/orders.http`, `requests/scenarios.http`, and `requests/validation.http`.
  - File is produced by running `scripts/generate_postman.py` (regeneration reproduces an equivalent file).
- **Brief**: Run the T003 generator to produce the committed artifact. This is the importable output users consume; it must round-trip with the generator so it can be regenerated when `.http` files change.

## T005 — CI workflow with Tailscale to local Postgres (.github/workflows/ci.yml)
- **Status**: [x]
- **Phase**: CI via Tailscale
- **Milestone**: ci-tailscale
- **Spec requirement**: R2.1, R2.2, R2.3, R2.4
- **Goal signals**: S3
- **Scope**: .github/workflows/ci.yml
- **Done when**:
  - `.github/workflows/ci.yml` exists, is valid YAML, and triggers on `pull_request` and `push` to `main`.
  - Job installs `uv`, runs `uv sync --extra dev`, runs `ruff check`, then runs the test suite (`uv run pytest`).
  - Uses the Tailscale GitHub Action authenticated with secret `TAILSCALE_AUTHKEY`, and includes a step that waits for the developer's node to be reachable before tests run.
  - Sets `DATABASE_URL` and `TEST_DATABASE_URL` env from secrets `DB_URL` and `TEST_DB_URL`; defines NO Postgres `services:` container.
  - Test execution is gated by a `RUN_TESTS` variable defaulting to `true`; when `false`, lint still runs but the test step is skipped. The job's success/failure surfaces as a PR status check.
  - `actionlint .github/workflows/ci.yml` (or YAML lint) reports no errors if available; otherwise the file parses as valid YAML.
- **Brief**: Do not add a Postgres service container — CI relies entirely on the developer's local DB over Tailscale. Reachability wait should poll the Tailscale host/port from `DB_URL`. Use `${{ vars.RUN_TESTS != 'false' }}` style gating so maintainers flip the repo/workflow variable without editing the file.

## T006 — Tailscale CI guide and README cross-link (docs/ci-tailscale.md)
- **Status**: [x]
- **Phase**: CI via Tailscale
- **Milestone**: ci-tailscale
- **Spec requirement**: R2.3, R2.5
- **Goal signals**: S4
- **Scope**: docs/ci-tailscale.md, README.md
- **Done when**:
  - `docs/ci-tailscale.md` exists and documents: how to create the Tailscale auth key, what `TAILSCALE_AUTHKEY` is, ensuring the developer machine is reachable on Tailscale, the required GitHub secrets (`TAILSCALE_AUTHKEY`, `DB_URL`, `TEST_DB_URL`), and the `RUN_TESTS` opt-out switch (default ON).
  - `README.md` contains a link to `docs/ci-tailscale.md`.
  - Steps in the guide match the secret/variable names used in `.github/workflows/ci.yml`.
- **Brief**: Reader-facing setup guide so a maintainer can stand up the CI from scratch. Keep secret/variable names exactly consistent with T005. Add a short "Continuous integration" reference in the README linking to this guide.

## T007 — Design decisions document (DESIGN_DECISIONS.md)
- **Status**: [x]
- **Phase**: Design decisions document
- **Milestone**: design-docs
- **Spec requirement**: R3.1, R3.2, R3.3, R3.4
- **Goal signals**: S5
- **Scope**: DESIGN_DECISIONS.md
- **Done when**:
  - `DESIGN_DECISIONS.md` exists with a per-choice section for each of: FastAPI, PostgreSQL + pgvector, SQLAlchemy async + asyncpg, Alembic, APScheduler, MCP, A2A, AG-UI/SSE, uv, pytest, ruff, and the LM Studio Anthropic-compatible endpoint.
  - Each choice section states the decision, the rationale, and alternatives considered / trade-offs.
  - An "Anticipated questions" section covers architecture, data model, concurrency/async, scheduler & order lifecycle, validation, testing strategy, agent/protocol layer, scaling, and security — each with a concise answer.
  - The document contains NO occurrence of: interviewer, interviewee, candidate, hiring, or "home assignment" (neutral framing verified by text search).
- **Brief**: Neutral engineering rationale document. Ground each section in the actual stack from `pyproject.toml`, `src/`, and `.specify/preferences.md`. Write as ordinary project documentation — no reference to any assignment, reviewer, or author context.

## T008 — README cross-link to design decisions (README.md)
- **Status**: [x]
- **Phase**: Design decisions document
- **Milestone**: design-docs
- **Spec requirement**: R3.5
- **Goal signals**: S5
- **Scope**: README.md
- **Done when**:
  - `README.md` contains a link to `DESIGN_DECISIONS.md` in a discoverable location (e.g. a "Design & architecture" or documentation section).
  - The link target path matches the file created in T007.
- **Brief**: Small README edit adding a discoverable link to the design decisions document. Keep it adjacent to other documentation links (including the CI guide from T006).
