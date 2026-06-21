# Feature goal — setup-ci-docs

## User goal
A new contributor runs one setup script and lands on a working local EC-OPS server with a ready-to-import Postman collection and clear next-step guidance. Every pull request automatically runs lint and tests against the developer's real PostgreSQL over Tailscale (skippable via a documented switch), and the repository contains a neutral document explaining every technical choice.

## Success signals
<!-- Each signal is an observable user-facing outcome. Checked off by the orchestrator after each phase. -->
- [ ] S1: Running `uv run python scripts/setup.py` on a clean checkout installs deps, creates `.env`, sets up the DB, and prints a "what to do next" guide with the local URL and request instructions — and re-running it is safe (idempotent).
- [ ] S2: A user can import `requests/EC-OPS.postman_collection.json` into Postman, set `baseUrl`, and fire every documented endpoint; `scripts/generate_postman.py` regenerates it from the `.http` files.
- [ ] S3: Opening a pull request triggers a GitHub Actions check that connects to the developer's local Postgres via Tailscale, runs `ruff check` and the test suite, and reports pass/fail as a PR status — skippable when `RUN_TESTS` is set to `false`.
- [ ] S4: `docs/ci-tailscale.md` explains the Tailscale auth key, machine reachability, required GitHub secrets, and the opt-out switch, and is linked from the README.
- [ ] S5: `DESIGN_DECISIONS.md` documents the decision, rationale, and alternatives for every key tool plus an "anticipated questions" section, in strictly neutral framing, and is linked from the README.

## Spec coverage
<!-- Maps each signal to the spec requirements it satisfies -->
S1 → spec req: R1.1, R1.2, R1.3, R1.5
S2 → spec req: R1.3, R1.4
S3 → spec req: R2.1, R2.2, R2.3, R2.4
S4 → spec req: R2.5
S5 → spec req: R3.1, R3.2, R3.3, R3.4, R3.5

## Goal progress
<!-- Updated by orchestrator after each phase completes -->
(not started)
