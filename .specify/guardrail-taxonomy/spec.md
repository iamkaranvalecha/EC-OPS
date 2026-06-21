# Spec — 9-Category Guardrail Taxonomy

## Original request

> Implement a 9-category guardrail taxonomy for the EC-OPS agent. Reference:
> the AISecOps attack library at
> `D:\Projects\personal\AISecOps\src\aisecops\attacks\library`.

## Background

EC-OPS currently has a single `InputGuardrail` (`src/agent/guardrails.py`) that
runs a flat list of ~16 regex injection patterns and returns one of three
reasons: `too_long`, `injection`, or `out_of_scope`. Every blocked attack —
whether a DAN jailbreak, a CEO-impersonation social-engineering attempt, or a
fake conversation-history injection — collapses into the single bucket
`injection`. There is no per-category classification, no telemetry on *which*
threat class was seen, and no coverage at all for attacks that arrive through
tool output rather than the user turn.

The AISecOps reference library defines nine threat categories, each with a set
of representative payloads, expected-failure indicators, and severity hints.
This feature brings that taxonomy into EC-OPS as a first-class, testable
classification layer.

## The nine categories (from the AISecOps library)

| # | Category | Where it arrives | Detectable pre-LLM? |
|---|----------|------------------|---------------------|
| 1 | `prompt_injection`    | user turn        | Yes — instruction-override / system-prompt-extraction patterns |
| 2 | `indirect_injection`  | **tool output / retrieved content** | Only by scanning tool results |
| 3 | `jailbreak`           | user turn        | Yes — persona (DAN/OPPO), fictional-framing, encoding patterns |
| 4 | `social_engineering`  | user turn        | Partial — authority + urgency + impersonation cues |
| 5 | `tool_misuse`         | user turn        | Partial — privilege-escalation / cross-user / auth-bypass cues |
| 6 | `data_exfiltration`   | user turn        | Partial — bulk-PII / credential / schema extraction cues |
| 7 | `goal_hijacking`      | user turn        | Partial — purpose-redefinition / priority-override cues |
| 8 | `context_poisoning`   | user turn **or** tool output | Yes — fake system/state/credential declarations |
| 9 | `history_injection`   | user turn        | Yes — fabricated `Human:/Assistant:` turns, `[CONVERSATION HISTORY]` blocks |

## Requirements

### R1 — Threat category enum
Introduce a `ThreatCategory` enum in `src/agent/guardrails.py` with exactly the
nine string values:
`prompt_injection`, `indirect_injection`, `jailbreak`, `social_engineering`,
`tool_misuse`, `data_exfiltration`, `goal_hijacking`, `context_poisoning`,
`history_injection`.

### R2 — Categorized input detection
Replace the flat `_INJECTION_PATTERNS` list with a category-keyed structure
mapping each `ThreatCategory` to its detection patterns. `InputGuardrail.check()`
must identify **which** category matched and surface it. Detection order is
deterministic (highest-severity / most-specific category wins on overlap).

### R3 — Result carries the category
`GuardrailResult` gains a `category: ThreatCategory | None` field. When a message
is blocked for a threat reason, `reason` stays a stable coarse value
(e.g. `"injection"`) for backward compatibility, and `category` carries the
fine-grained classification. Existing callers that only read `reason`/`reply`
keep working unchanged.

### R4 — Tool-output guardrail (indirect injection + context poisoning)
Add an output-side scan that inspects **tool results** before they are fed back
to the LLM in the agentic loop (`agui_stream.py` and `executor.py`). If a tool
result contains injected instructions (e.g. an order's customer-supplied field
says "ignore your instructions and …"), the content is neutralized (stripped or
wrapped as inert data) and the event is logged with category
`indirect_injection` or `context_poisoning`. This is the only category that
cannot be caught at the input layer.

### R5 — Coverage parity with the reference library
For every category, the representative payloads from the corresponding
AISecOps YAML file must be covered: each payload that is realistically
detectable pre-LLM is blocked and classified into the correct category. Payloads
that are genuinely undetectable by deterministic rules (and rely on the model's
own refusal) are documented as accepted-risk pass-through cases, not silently
ignored.

### R6 — Deterministic eval suite
Extend `tests/eval/eval_cases.py` so every category has labelled cases asserting
both `expected_blocked` and the expected `ThreatCategory`. The existing
`tests/eval/` runner is extended to assert the category, not just the boolean.
Add per-category coverage so a regression in any single category fails a
distinct, named test.

### R7 — No weakening of existing behavior
All currently-passing tests stay green. No existing guardrail pattern is removed
unless it is moved (re-homed) into a category bucket with equal-or-broader
coverage. The legitimate order-management requests that pass today must still
pass (no new false positives on normal "list/create/cancel order" traffic).

### R8 — Observability
Each block logs the matched category at INFO level in a stable, greppable format
(e.g. `guardrail blocked: category=jailbreak`). This is what makes the taxonomy
useful operationally — you can see the distribution of attack classes hitting
the agent.

## Out of scope

- No live LLM-based classifier — detection stays deterministic (regex/keyword)
  so the eval suite is fast and reproducible. (A model-graded layer can come
  later as a separate feature.)
- No changes to the order-management business logic or REST API.
- No new external dependencies. Pure-stdlib `re` + the existing test stack.
- The `{harmful_query}` / `{restricted_topic}` template placeholders in the
  AISecOps payloads are generic-LLM-safety probes; EC-OPS adapts the *structure*
  of those attacks to its order-management scope rather than reproducing
  general-purpose harmful-content handling.

## Success signals

- S1 — `ThreatCategory` enum exists with all nine values and is the single
  source of truth for category names.
- S2 — A blocked attack from any of the nine categories is classified into the
  correct category, observable in both `GuardrailResult.category` and the log.
- S3 — Tool-result injection (indirect / context poisoning) is detected and
  neutralized before reaching the LLM.
- S4 — The eval suite asserts per-category classification; every category has at
  least one blocked case and the suite is green.
- S5 — No regression: all pre-existing tests pass and no new false positives on
  normal order traffic.
