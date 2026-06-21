# Tasks

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — Full codebase audit (read-only matrix)
- **Status**: [x]
- **Phase**: Audit
- **Scope**: src/**/*.py, tests/**/*.py, scripts/generate_insomnia.py
- **Done when**:
  - Every file is read line by line.
  - Matrix produced with File, Line(s), Severity, Category, Bug, Impact, Fix columns.
  - At least one CRITICAL and one HIGH finding identified.
- **Result**: 24 findings across 15 files. 1 CRITICAL, 6 HIGH, 8 MEDIUM, 9 LOW.
  Audit performed by a forked agent reading all 40+ source and test files.

## T002 — Fix: `_TRACEBACK_RE` greedy regex eats text after traceback
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: MEDIUM
- **Category**: Logic
- **Scope**: `src/agent/guardrails.py:31`
- **Done when**:
  - `_TRACEBACK_RE` uses `.*?(?=\n\n|\Z)` (non-greedy, stops at blank line or end).
  - Text after a blank-line-separated traceback is preserved.
  - 176 tests pass.

## T003 — Fix: `_ReasoningFilter` unclosed `<think>` tag drops all subsequent text
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: MEDIUM
- **Category**: Logic
- **Scope**: `src/agent/agui_stream.py:66–96`
- **Done when**:
  - `_ReasoningFilter` has a `flush()` method that emits held tail regardless of `_in_think`.
  - `flush()` is called after the `text_stream` loop, before `get_final_message()`.
  - If model never closes `<think>`, buffered text is discarded rather than silently lost.
  - 176 tests pass.

## T004 — Fix: `ToolCallStart` emitted before tool-count limit check
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: MEDIUM
- **Category**: Logic
- **Scope**: `src/agent/agui_stream.py:182–194`
- **Done when**:
  - Per-tool count incremented and checked **before** `yield ToolCallStart`.
  - When limit exceeded: emit `TextDelta` and return without ever yielding `ToolCallStart`.
  - No dangling ToolCallStart events possible.
  - 176 tests pass.

## T005 — Fix: misleading iteration counter in `finally` log
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: LOW
- **Category**: Logic
- **Scope**: `src/agent/agui_stream.py:127, 255`
- **Done when**:
  - `iteration = 0` replaced with `_iterations_run = 0`.
  - Counter incremented at the top of the `for` loop body.
  - `finally` log uses `_iterations_run` (0 when guardrail blocks, accurate otherwise).
  - 176 tests pass.

## T006 — Fix: unguarded `UUID()` parse in `get_order_tool` and `cancel_order_tool`
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: HIGH
- **Category**: Error Handling
- **Scope**: `src/agent/tools.py:81, 138`
- **Done when**:
  - Both tools parse `UUID(order_id)` in a dedicated `try/except ValueError` before
    entering the session context manager.
  - A bad UUID string from the LLM produces a clean `ValueError` with a human-readable
    message, not raw Python exception text.
  - 176 tests pass.

## T007 — Fix: `executor.py` returns empty string when `end_turn` has no text block
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: MEDIUM
- **Category**: Logic
- **Scope**: `src/agent/executor.py:119–127`
- **Done when**:
  - When `stop_reason in ("end_turn", "stop")` produces `text = ""`, a warning is logged
    and a fallback message is returned instead of an empty string.
  - 176 tests pass.

## T008 — Fix: `OrderNotFound` / `OrderNotCancellable` embed full UUID in message
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: MEDIUM
- **Category**: Security
- **Scope**: `src/orders/exceptions.py:2–8`
- **Done when**:
  - Both exception constructors truncate `order_id` to `str(order_id)[:8] + "..."`.
  - Full UUID no longer reaches tool error content before `OutputSanitizer` runs.
  - 176 tests pass.

## T009 — Fix: `asyncio.create_task` return value discarded in `a2a_router.py`
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: HIGH
- **Category**: Race Condition
- **Scope**: `src/agent/a2a_router.py:22, 109`
- **Done when**:
  - `_task_handles: dict[str, asyncio.Task] = {}` added at module level.
  - `send_task` stores: `_task_handles[task_id] = asyncio.create_task(...)`.
  - `_run_task` cleans up: `finally: _task_handles.pop(task_id, None)`.
  - In-flight tasks are no longer eligible for GC during reload/SIGTERM.
  - 176 tests pass.

## T010 — Fix: `skipif` in integration tests accepts `DATABASE_URL` as qualifying condition
- **Status**: [x]
- **Phase**: Code fixes
- **Severity**: LOW
- **Category**: Test Integrity
- **Scope**: `tests/orders/test_models.py:94`, `tests/orders/test_service.py:180`
- **Done when**:
  - Both `skipif` conditions check only `not os.environ.get("TEST_DATABASE_URL")`.
  - `DATABASE_URL` alone is no longer sufficient to un-skip the tests.
  - The skip message says "requires live test DB — set TEST_DATABASE_URL to run".
  - 176 tests pass.

## T011 — Verify: full test suite green after all fixes
- **Status**: [x]
- **Phase**: Verification
- **Scope**: tests/
- **Done when**:
  - `uv run pytest tests/ -q` outputs `176 passed`.
  - No previously passing test was broken by any fix.
- **Result**: `176 passed in 86.52s` ✓

## T012 — Update `.specify` and docs
- **Status**: [x]
- **Phase**: Documentation
- **Scope**: .specify/bug-fixes-audit/, README.md, ARCHITECTURE.md, DESIGN_DECISIONS.md
- **Done when**:
  - `.specify/bug-fixes-audit/` contains `goal.md`, `spec.md`, `plan.md`, `tasks.md`.
  - `README.md` test count updated (161 → 176), Postman references updated to Insomnia,
    VS Code tasks table corrected, bug-fixes section added.
  - `DESIGN_DECISIONS.md` gets a new section 15 covering the bug-audit findings
    and the architectural decisions deferred.
  - `ARCHITECTURE.md` reflects any structural changes since last update.
