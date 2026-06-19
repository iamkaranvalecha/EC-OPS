---
description: Full orchestrator — auto-detects the active feature from .specify/current, reads the next task from that feature's tasks.md (or takes a description as $ARGUMENTS), tracks it on GitHub, and runs the build→check→review loop.
argument-hint: [task description] (optional — reads next incomplete task from tasks.md if omitted)
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
model: opus
---

You are the task-level orchestrator. You run one task to completion or surface a
clear, actionable blocker to the human.

**No assumptions.** Verify actual state at every step. Re-read every file fresh —
never carry state from a previous run.

---

## Phase 0 — Verify state, resolve feature, resolve task

### Verify environment first

**Conflict state check — run first:**
```bash
ls .git/MERGE_HEAD .git/REBASE_HEAD .git/CHERRY_PICK_HEAD .git/REVERT_HEAD 2>/dev/null
```
If any file exists: **STOP.**
```
Branch is in conflict state. Resolve or abort first, then re-run /speckit-loop.
```

```bash
git status --short
git branch --show-current
ls .specify/ 2>/dev/null || echo "NO_SPECIFY_DIR"
```

If `.specify/` does not exist: stop —
"No .specify/ directory found. Run /plan <feature description> first."

If git is not available or not a repo: stop and report.

Note any uncommitted changes — do not assume the working tree is clean.

### Determine the active feature directory

If $ARGUMENTS starts with a known feature slug (matches a `.specify/<slug>/`
directory): use `.specify/<slug>/` as FEATURE_DIR. Treat remaining $ARGUMENTS
as the task description (may be empty).

Otherwise, check `.specify/current`:
```bash
cat .specify/current 2>/dev/null
```
If the file exists and the slug matches an actual directory under `.specify/`:
use `.specify/<slug>/` as FEATURE_DIR.

If `.specify/current` is missing or points to a non-existent directory:
list what actually exists:
```bash
ls -d .specify/*/ 2>/dev/null
```
- If exactly one subdirectory: use it and note which one.
- If multiple: print the list and ask the human which feature to work on. Stop until answered.
- If none: stop — "No feature directories found. Run /plan first."

### Verify the feature directory is complete

```bash
ls "$FEATURE_DIR/spec.md" "$FEATURE_DIR/tasks.md" 2>/dev/null | wc -l
```
If not 2: stop — list which files are missing. The human may need to re-run
`/plan` or restore the files.

Read `$FEATURE_DIR/goal.md` if it exists. Extract:
- `USER_GOAL` — the one or two sentence user goal statement
- `PENDING_SIGNALS` — the `[ ]` success signals not yet marked done

If `goal.md` does not exist: set USER_GOAL to "" and PENDING_SIGNALS to "".
Do not fail — goal tracking is advisory, not required.

Also verify `.specify/preferences.md` exists:
```bash
ls .specify/preferences.md 2>/dev/null || echo "MISSING"
```
If missing: warn the human and proceed without preferences context (do not fail).

### Lightweight drift check (Tier 1 only)

Check for fingerprint:
```bash
ls "$FEATURE_DIR/.fingerprint" 2>/dev/null || echo "NO_FINGERPRINT"
```

If NO_FINGERPRINT: skip. Print `Drift: no fingerprint — skipping check.`

If fingerprint exists, check only the SCOPE files for the task being worked on.
Extract the task's SCOPE paths from the fingerprint `tasks:` block matching TASK_ID.

Batch check those paths:
```bash
git ls-files -s <task SCOPE files> 2>/dev/null
```

For each path:
- `blob:<SHA>` in fingerprint AND current blob differs AND not whitespace-only → warn:
  ```
  ⚠ Drift detected: <file> changed since it was last fingerprinted.
  This may affect what you're about to build. Check the diff:
    git diff <fingerprinted_blob>..HEAD -- <file>
  Proceeding — but flag this to the reviewer.
  ```
  Do NOT stop — just warn and pass the drift info to the builder and reviewer.
- `not_yet_created` → expected, skip.
- File deleted (blob check returns empty) → warn as HIGH, include in task brief.

### Resolve the task

If a task description was extracted from $ARGUMENTS, use it. Set TASK_ID to "".

If no task description, re-read `$FEATURE_DIR/tasks.md` fresh and find the first `[ ]` task:
- TASK_ID from the `## TXXX —` heading
- TASK_TITLE from text after `—`
- MILESTONE from `- **Milestone**:`
- SPEC_REQ from `- **Spec requirement**:`
- SCOPE from `- **Scope**:`
- DONE_WHEN from `- **Done when**:`
- ISSUE_NUM from `- **Issue**: #<N>` (if present in the task block; else set to "")

If no `[ ]` task exists: check for `[~]` (blocked) tasks. If any exist, list them
and ask the human if they want to retry one. If none at all: stop — "All tasks
complete for this feature."

Set SPEC_PATH = `$FEATURE_DIR/spec.md` and TASKS_PATH = `$FEATURE_DIR/tasks.md`.

## Phase 1 — Write task brief

```
Goal: <TASK_TITLE>
Spec requirement: <SPEC_REQ>
Goal signals this task advances: <from task's Goal signals field, or "see goal.md">
User goal: <USER_GOAL — if available>
Pending signals not yet met: <PENDING_SIGNALS — if available>
Scope: <SCOPE>
Done when: <DONE_WHEN>
```

## Phase 2 — Create GitHub issue

If ISSUE_NUM is already set (read from `- **Issue**: #<N>` in Phase 0): skip CREATE_ISSUE.
Print: `GitHub issue: #<ISSUE_NUM> (already tracked — skipping duplicate creation)`

Otherwise dispatch tracker:
```
CREATE_ISSUE title="<TASK_ID>: <TASK_TITLE>" milestone="<MILESTONE>" body="<task brief>"
```
Set ISSUE_NUM from output or "N/A" if GITHUB_UNAVAILABLE.

If ISSUE_NUM ≠ "N/A" and was freshly created: append `- **Issue**: #<ISSUE_NUM>` to the task
block in `$TASKS_PATH` (after the `- **Done when**:` line). This lets `/resume` skip
re-creating the issue on the next session.

## Phase 3 — Build → Check → Review loop

Initialise empty failure log. Set cycle = 1. Set prev_failures = "".

**Loop (up to 5 cycles):**

### 3a — Build

Dispatch builder. On cycle 1:
```
Task brief:
<task brief>

Full spec (keep the big picture in mind):
<contents of $SPEC_PATH>

User goal (keep this in view — the code must help reach it):
<USER_GOAL and PENDING_SIGNALS if available>

Preferences:
<stack, db, auth, test_strategy from .specify/preferences.md>
```

On cycle > 1:
```
--- Failure history (what has already been tried) ---
<full failure log>

--- Current failures (fix only these) ---
<latest failures>

--- Task brief ---
<task brief>

--- Full spec (keep the big picture in mind) ---
<contents of $SPEC_PATH>
```

### 3b — Check

Dispatch checker (detects toolchain automatically).

### 3c — Evaluate

**If INFRA_FAILURE:** — stop immediately, do not retry.
Go to Phase 4 with stop reason: `"Infrastructure not ready: <checker's error line>. Fix the environment (start Docker, set DB connection string, install missing tool) and re-run."`

**If FAILED:**
- Append to failure log: `[Cycle N] <failures>`
- Check stop conditions (CLAUDE.md):
  - cycle = 5 → BLOCKED: "5 cycles used"
  - failures = prev_failures → BLOCKED: "Same failure twice — builder is stuck"
  - previously passing check now fails → BLOCKED: "Fix broke a passing check"
- Else: set prev_failures, increment cycle, go to 3a.

**If ALL GREEN:**
- Tracker: `UPDATE_LABEL issue=<N> remove="in-progress" add="needs-review"` (if available)
- Go to 3d.


### 3d — Review

Dispatch reviewer with task brief, the contents of `$SPEC_PATH`, and the
user goal + pending signals from `$GOAL_PATH` so it can check both spec
alignment and goal progress.

**If APPROVED:** go to Phase 5.

**If ISSUES FOUND:**
- Append to failure log: `[Cycle N] [review] <issues>`
- Check stop conditions.
- Else: set prev_failures, increment cycle, go to 3a.

---

## Phase 4 — BLOCKED — escalate to human with full context

Compose this exact escalation message:

```
🚨 NEEDS YOUR INPUT — blocked on <TASK_ID>: <TASK_TITLE>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BIG PICTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Spec requirement this task covers:
  <SPEC_REQ — quote from spec.md>

Overall goal:
  <one-line goal from spec.md>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT WAS BEING BUILT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<task brief>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT WAS TRIED (full history)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<full failure log with all cycles>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOP REASON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<which stop condition triggered and why>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT I NEED FROM YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<specific question — e.g. "Should I approach the auth differently?
 Here are two options: (A) ... (B) ...">

GitHub issue: #<ISSUE_NUM> (labelled 'blocked')
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then:
- Tracker: `UPDATE_LABEL issue=<N> remove="in-progress" add="blocked"` (if available)
- Tracker: `COMMENT issue=<N> body="<escalation message>"` (if available)
- If TASK_ID set: mark `[~]` in `$TASKS_PATH`
- Stop.

---

## Phase 5 — Success

Mark `[x]` in `$TASKS_PATH` (if TASK_ID set); verify by re-reading that line.

Dispatch docs-writer with task brief + SCOPE files changed.

Print:
```
✅ <TASK_ID> COMPLETE

Cycles:  <N>
Checker: ALL GREEN
Reviewer: APPROVED
Spec req: <SPEC_REQ> ✓
Signals: <goal signals advanced>

Files:
  <list of SCOPE files created or modified>
```

Then run the § Commit flow (defined in plan.md — duplicated here for standalone use):

Read `commit_strategy` from `.specify/preferences.md` (default `ask` if absent).
Read `branch_strategy` from `.specify/preferences.md` (default `auto` if absent).

**If `commit_strategy: off`**: print the following and stop.
```
Files ready to commit manually:
  <SCOPE files>
  .specify/<FEATURE_SLUG>/tasks.md
  .specify/<FEATURE_SLUG>/.fingerprint
Push to remote on your schedule.
```

**Otherwise (ask or auto):**

**Step 1 — Pull**
```bash
git diff --cached --quiet || git restore --staged .
BRANCH=$(git branch --show-current)
git pull --rebase origin "$BRANCH" 2>&1
```
If non-zero exit: **STOP** — "Pull failed — resolve conflicts first, then re-run /speckit-loop."

**Step 2 — Branch** (if `branch_strategy: auto` and BRANCH is main/master/develop/trunk)
```bash
NEW_BRANCH="feat/<TASK_ID>-<task-title-lowercased-kebab>"
if git branch --list "$NEW_BRANCH" | grep -q .; then
  git checkout "$NEW_BRANCH"
  # Print: Switched to existing branch: $NEW_BRANCH
else
  git checkout -b "$NEW_BRANCH"
  # Print: Created branch: $NEW_BRANCH
fi
```
Update `BRANCH = NEW_BRANCH`.

**Step 3 — Stage SCOPE files**
```bash
git add <SCOPE files>
```

**Step 4 — Update fingerprint** (must run after step 3 so staged SHAs are available)
```bash
for file in <SCOPE files>; do
  blob=$(git ls-files -s "$file" 2>/dev/null | awk '{print $2}')
  [ -n "$blob" ] && sed -i "s|$(printf '%s\n' "$file" | sed 's/[[\.*^$()+?{|]/\\&/g'): not_yet_created|$(printf '%s\n' "$file" | sed 's/[[\.*^$()+?{|]/\\&/g'): blob:$blob|" "$FEATURE_DIR/.fingerprint" 2>/dev/null
done
```

**Step 5 — Stage .specify/ files**
```bash
git add ".specify/$FEATURE_SLUG/tasks.md" ".specify/$FEATURE_SLUG/.fingerprint"
```

**Step 6 — Build commit message**
```
<TASK_TITLE lowercased as imperative verb phrase>

Task:    <TASK_ID>
Spec:    <SPEC_REQ>
Signals: <goal signals advanced>
<if ISSUE_NUM ≠ N/A: "Closes: #<ISSUE_NUM>">
```
First line: lowercase TASK_TITLE; if it reads as a noun, prepend "implement".

**Step 7 — Commit**

If `commit_strategy: ask`:
```
Stage and commit? (yes / no / edit message)
  Branch:  <BRANCH>
  Files:   <SCOPE files + tasks.md + .fingerprint, one per line>
  Message: "<generated message>"
```
STOP and wait.
- `yes` → `git commit -m "<message>"`; capture SHA; print "Push to remote on your schedule."
- `no` → `git restore --staged .`; print "Unstaged. Commit manually when ready." Stop.
- `edit message` → STOP; on reply → `git commit -m "<user message>"`; capture SHA; print "Push to remote on your schedule."

If `commit_strategy: auto`:
```bash
git commit -m "<generated message>"
```
Capture SHA. Print: `Committed: <SHA> — <TASK_ID>: <TASK_TITLE>` · `Push to remote on your schedule.`

**Step 8 — Post review comment** (only if commit happened and ISSUE_NUM ≠ N/A)
```
COMMENT issue=<ISSUE_NUM> body="Committed <SHA> to `<BRANCH>`. Ready for your review.

Files: <SCOPE files, one per line>"
```

Also close the issue: `CLOSE_DONE issue=<ISSUE_NUM> body="<summary>"` (if available)

Always stage only the explicit SCOPE file list + tasks.md + .fingerprint. Never use `git add .` or `git add -A`.

Stop.

---

## Stop conditions (CLAUDE.md — enforced exactly)
- ALL GREEN + APPROVED → success
- 5 cycles → blocked
- Same failure twice → blocked
- Fix breaks passing check → blocked

Never report success without checker output. Never weaken a check.
