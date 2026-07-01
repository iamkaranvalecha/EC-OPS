# Tasks — guardrail-taxonomy

<!--
Status values:
  [ ] = not started
  [x] = done
  [~] = blocked (needs human)
speckit-loop picks the first [ ] task when run with no arguments.
-->

## T001 — Add ThreatCategory enum
- Status: [x]
- Phase: 1
- Milestone: mvp
- Spec requirement: R1
- Goal signals: S1
- Scope: `src/agent/guardrails.py`
- Done when: `ThreatCategory` (a `str`-valued `enum.Enum`) is defined in
  `src/agent/guardrails.py` and importable as `from src.agent.guardrails import ThreatCategory`;
  it has exactly nine members with these string values — `prompt_injection`,
  `indirect_injection`, `jailbreak`, `social_engineering`, `tool_misuse`, `data_exfiltration`,
  `goal_hijacking`, `context_poisoning`, `history_injection`; `len(list(ThreatCategory)) == 9`
  and each member's `.value` equals its lowercase name; `ruff check src/agent/guardrails.py`
  passes; the existing `pytest tests/ -q` stays green (additive change only).

## T002 — Categorize input patterns
- Status: [x]
- Phase: 1
- Milestone: mvp
- Spec requirement: R2
- Goal signals: S2, S5
- Scope: `src/agent/guardrails.py`
- Done when: the flat `_INJECTION_PATTERNS: list[re.Pattern]` is replaced by
  `_PATTERNS_BY_CATEGORY: list[tuple[ThreatCategory, list[re.Pattern]]]`, ordered highest-severity
  first (jailbreak, prompt_injection, history_injection, context_poisoning, goal_hijacking,
  tool_misuse, data_exfiltration, social_engineering, indirect_injection user-side); all 15
  existing patterns are re-homed into categories with no pattern deleted and no coverage gap;
  `InputGuardrail.check()` iterates `_PATTERNS_BY_CATEGORY` in order and returns on the first
  matching category; every prompt the old list blocked is still blocked (verify via
  `pytest tests/eval/ -m eval -q`); `ruff check src/agent/guardrails.py` passes.

## T003 — Add category to GuardrailResult
- Status: [x]
- Phase: 1
- Milestone: mvp
- Spec requirement: R3
- Goal signals: S2, S5
- Scope: `src/agent/guardrails.py`
- Done when: `GuardrailResult` gains a `category: ThreatCategory | None = None` field (last field,
  defaulted, so existing construction is unaffected); `InputGuardrail.check()` populates
  `category` with the matched `ThreatCategory` on every injection block while `reason` stays the
  literal `"injection"`; non-injection results (`too_long`, `out_of_scope`, pass-through) leave
  `category=None`; assert `result.category is not None` and `result.reason == "injection"` for an
  injection prompt; full `pytest tests/ -q` stays green; `ruff check src/agent/guardrails.py`
  passes.

## T004 — Tool-output guardrail
- Status: [x]
- Phase: 2
- Milestone: mvp
- Spec requirement: R4
- Goal signals: S2, S3, S5
- Scope: `src/agent/guardrails.py` (new `ToolOutputGuardrail` class), `src/agent/agui_stream.py`,
  `src/agent/executor.py`
- Done when: a new `ToolOutputGuardrail` class in `guardrails.py` exposes a `scan(output: str)`
  (or equivalent) method that runs the injection patterns over a tool-result string and returns a
  `GuardrailResult(blocked=True, category=ThreatCategory.INDIRECT_INJECTION)` (or
  `CONTEXT_POISONING` for fake system/state/credential declarations) on a match, else
  `GuardrailResult(blocked=False)`; both `agui_stream.py` and `executor.py` instantiate it once at
  module scope and call it on the `output` string immediately before the `tool_results.append({...})`
  in their agentic loop; on a block, the appended tool-result `content` is replaced with a safe
  inert string (e.g. `"[tool output withheld: potential injected instructions removed]"`) so the
  malicious text never reaches the LLM; clean tool results are appended unchanged (no regression);
  a tool result string containing `"ignore your instructions"` is caught and neutralized in both
  loops; `pytest tests/ -q` stays green; `ruff check src/agent/guardrails.py src/agent/agui_stream.py src/agent/executor.py`
  passes.

## T005 — Observability: structured logging
- Status: [x]
- Phase: 1
- Milestone: mvp
- Spec requirement: R8
- Goal signals: S2
- Scope: `src/agent/guardrails.py`
- Done when: every input-layer injection block emits a single INFO log line in the exact stable
  format `logger.info("guardrail blocked: category=%s", category.value)`, and every tool-output
  block (from T004) emits `logger.info("tool-output guardrail: category=%s", category.value)`;
  the substring `guardrail blocked: category=` is greppable on every injection block and
  `tool-output guardrail: category=` on every tool-output block (verify with caplog at INFO
  level); no log line is emitted for pass-through results; `pytest tests/ -q` stays green;
  `ruff check src/agent/guardrails.py` passes.

## T006 — Extend eval cases
- Status: [x]
- Phase: 2
- Milestone: mvp
- Spec requirement: R5, R6
- Goal signals: S4
- Scope: `tests/eval/eval_cases.py`, `tests/eval/test_guardrails_eval.py`
- Done when: `EvalCase` gains `expected_category: ThreatCategory | None = None`;
  `GUARDRAIL_CASES` is extended so every one of the nine `ThreatCategory` members has at least one
  blocked case labelled with its `expected_category` (at least two cases per category overall: one
  blocked+labelled, plus a pass-through where a realistic legitimate look-alike applies),
  porting representative payloads from the AISecOps YAML files (`prompt_injection.yaml`,
  `indirect_injection.yaml`, `jailbreak.yaml`, `social_engineering.yaml`, `tool_misuse.yaml`,
  `data_exfiltration.yaml`, `goal_hijacking.yaml`, `context_poisoning.yaml`,
  `history_injection.yaml`) adapted to order-management scope; genuinely undetectable payloads are
  added as documented accepted-risk pass-through cases, not omitted; `test_guardrails_eval.py`
  asserts `result.category == case.expected_category` whenever `expected_category` is set (and
  imports `ThreatCategory`); a per-category coverage check ensures each of the nine categories has
  at least one labelled blocked case so a regression in any single category fails a distinct named
  assertion; `pytest tests/eval/ -m eval -q` exits 0; `ruff check tests/eval/` passes.

## T007 — Full test suite: no regression
- Status: [x]
- Phase: 2
- Milestone: mvp
- Spec requirement: R7
- Goal signals: S5
- Scope: test runner only (no source or test-file edits)
- Done when: `pytest --tb=short -q` exits 0 and `pytest -m eval -q` exits 0; no pre-existing test
  was weakened, skipped, or deleted to reach green; no new false positives on the existing
  legitimate order-traffic pass-through cases (`list all orders`, `create an order …`,
  `cancel order …`, etc.) — they remain `expected_blocked=False`; `ruff check src tests` passes.
