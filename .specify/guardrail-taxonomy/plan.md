# Implementation Plan — guardrail-taxonomy

Stack: Python 3.12 + FastAPI · pytest + pytest-asyncio + httpx · ruff · uv · no new dependencies (pure-stdlib `re` only)

Structure: `src/` (feature-based) · tests mirror src under `tests/` · file_naming snake_case · vars snake_case · classes PascalCase · constants UPPER_SNAKE_CASE

## Overview

Today `src/agent/guardrails.py` runs a flat `_INJECTION_PATTERNS` list and collapses every
blocked attack into the single coarse reason `"injection"`. This feature layers a 9-category
taxonomy on top of the existing detection without changing its coarse contract: the same
attacks stay blocked, the same `reason` strings are returned, but each block now also carries a
fine-grained `ThreatCategory` that is logged and asserted in the eval suite. It also adds the one
category the input layer structurally cannot catch — injection that arrives through **tool
output** — by scanning tool results in the agentic loop before they are fed back to the LLM.

## Phase 1 — Core taxonomy
Milestone: mvp
Goal: classify every input-layer block into one of nine named categories, surfaced on
`GuardrailResult.category` and in a stable greppable log line, with zero behavioural regression.
Spec requirements covered: R1, R2, R3, R8 (input side)
Success signals advanced: S1, S2, S5
Tasks: T001, T002, T003, T005

## Phase 2 — Tool-output guardrail + eval coverage
Milestone: mvp
Goal: detect and neutralize indirect-injection / context-poisoning that arrives via tool
results, and extend the deterministic eval suite to assert per-category classification with the
full suite green.
Spec requirements covered: R4, R5, R6, R7, R8 (tool-output side)
Success signals advanced: S2, S3, S4, S5
Tasks: T004, T006, T007

## Key design decisions

1. **Category-keyed pattern map (R2).** `_INJECTION_PATTERNS: list[Pattern]` is replaced by
   `_PATTERNS_BY_CATEGORY: list[tuple[ThreatCategory, list[Pattern]]]`. A list of tuples (not a
   dict) because **detection order is part of the contract** — the first category whose pattern
   matches wins, so the list is ordered highest-severity / most-specific first:
   `jailbreak > prompt_injection > history_injection > context_poisoning > goal_hijacking >
   tool_misuse > data_exfiltration > social_engineering > indirect_injection`. Every one of the
   existing 15 patterns is re-homed into a category with no coverage gap (R7) — none is deleted,
   only moved.

2. **Backward-compatible coarse `reason` (R3).** `GuardrailResult` gains
   `category: ThreatCategory | None = None` as the last field with a default, so existing
   positional/keyword construction keeps working. On an injection block, `reason` stays the
   stable `"injection"` value and `category` carries the fine-grained class. Callers in
   `agui_stream.py` / `executor.py` that read only `reason` / `reply` are untouched.

3. **Detection ordering = severity ordering.** The same message can match several categories
   (e.g. a DAN jailbreak that also extracts a system prompt). The ordered list guarantees a
   deterministic, severity-first classification so eval cases assert one stable category per
   prompt.

4. **Tool-output scan hook (R4).** A new `ToolOutputGuardrail` reuses the injection patterns to
   scan the `output` string built for each tool result in **both** agentic loops — in
   `agui_stream.py` and `executor.py`, at the point right before the `tool_results.append({...})`
   call. If a tool result string matches, the caller replaces the tool-result content with a safe
   inert string before it is appended to `messages`, and logs the block. This is the only
   category pair (`indirect_injection` / `context_poisoning`) that cannot be caught pre-LLM
   because the malicious text originates in retrieved/customer-supplied data, not the user turn.

5. **Observability (R8).** Every block — input and tool-output — emits a single stable,
   greppable INFO line: `guardrail blocked: category=<value>` for input blocks and
   `tool-output guardrail: category=<value>` for tool-output blocks. The line is keyed on
   `category.value` (the enum's string value) so the operational distribution of attack classes
   is greppable from logs without parsing.

6. **Deterministic eval only.** No LLM-graded classification (out of scope). Coverage parity with
   the AISecOps library (R5) is achieved by porting representative payloads per category into
   `eval_cases.py`: detectable payloads as blocked+expected-category cases, genuinely
   undetectable ones as documented accepted-risk pass-through cases — never silently dropped.
