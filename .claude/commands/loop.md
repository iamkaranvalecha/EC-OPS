---
description: Run the builder and checker in a loop until all checks pass, then review the diff
argument-hint: <task>
allowed-tools: Read, Grep, Glob, Bash, Task
model: opus
---

Run this task as a loop: $ARGUMENTS

Before starting, initialise an empty failure log: a list of entries in
the format `[Cycle N] <failures>`.

1. Write a one-line brief: goal, files in scope, definition of done.
2. Dispatch the builder to implement the task.
3. Dispatch the checker to run all checks.
4. If checker says ALL GREEN:
   a. Dispatch the reviewer with the task brief so it knows what was in scope.
   b. If reviewer says APPROVED: stop and report success with checker output
      and reviewer verdict as proof.
   c. If reviewer says ISSUES FOUND: append the issues to the failure log
      under the current cycle number (prefix with "[review]"), then dispatch
      the builder with the same failure history format as step 5b, then go
      back to step 3.
5. If checker says FAILED:
   a. Append the failures to the failure log under the current cycle number.
   b. Dispatch the builder with BOTH the new failures AND the full failure
      log so far, formatted as:

      --- Failure history ---
      [Cycle 1] <failures from cycle 1>
      [Cycle 2] [review] <reviewer issues from cycle 2>
      ...
      --- Current failures (fix these) ---
      <failures from this cycle>

      This lets the builder see what has already been tried and avoid
      repeating the same wrong fix.
   c. Go back to step 3.
6. Repeat up to 5 cycles. Track the cycle count out loud.

Stop conditions are in CLAUDE.md. Follow them exactly.
