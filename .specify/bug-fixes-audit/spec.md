# Spec — bug-fixes-audit

## Verbatim request

> look for bugs in solution. detailed research with matrix for every line of code

## Scope

All Python source files under `src/` and all test files under `tests/`,
plus generator scripts under `scripts/`.

## Audit requirements

- A-1 — Read every file line by line; produce a matrix with columns:
  File, Line(s), Severity (CRITICAL/HIGH/MEDIUM/LOW), Category, Bug, Impact, Fix.
- A-2 — Severity definitions:
  - CRITICAL: data loss, silent corruption, or broken in any realistic deployment.
  - HIGH: crashes on valid input, raw exception leakage, or security vulnerability.
  - MEDIUM: silent wrong output, protocol violation, or misleading log signal.
  - LOW: misleading test guard, stale count, minor behavioral surprise.
- A-3 — Categories: Logic | Security | Data Loss | Race Condition |
  Error Handling | Type Safety | Performance | Test Integrity | Config.
- A-4 — Only behavioral bugs, not style issues.

## Fix requirements

Apply all code-level fixes. Architectural issues (multi-worker A2A store,
`run_migrations` MCP exposure) are flagged but not changed — they require
a deployment decision.

After all fixes: `uv run pytest tests/` must pass with the same count as before.

## Out of scope

- Style, linting, refactoring.
- Architectural changes requiring new infrastructure (Redis, etc.).
- New features.
