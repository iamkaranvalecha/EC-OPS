# Goal — guardrail-taxonomy

## User goal

Every blocked attack is classified into one of nine named threat categories
(visible in logs and `GuardrailResult.category`), injections that arrive through
tool output are neutralized before they reach the LLM, and the eval suite asserts
per-category coverage so a regression in any single threat class fails a named
test immediately.

## Success signals

- [x] S1 — `ThreatCategory` enum exists with all nine values and is the single source of truth
- [x] S2 — A blocked attack from any category is classified into the correct one, observable in `GuardrailResult.category` and `guardrail blocked: category=<x>` log lines
- [x] S3 — Tool-result injection (indirect / context poisoning) is detected and neutralized before it is fed back to the LLM
- [x] S4 — Eval suite asserts per-category classification; every category has at least one labelled blocked case; suite is green
- [x] S5 — No regression: all pre-existing tests pass; no new false positives on normal order traffic

## Goal progress

All signals complete — feature shipped. 102 eval tests pass; `ThreatCategory` enum, `ToolOutputGuardrail`, and per-category logging all in production.
