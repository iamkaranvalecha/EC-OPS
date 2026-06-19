---
description: Full end-to-end pipeline — bootstraps a per-feature spec directory, discovers stack via spec analysis, lets the human edit the spec, shows the plan for approval, then builds every task automatically with spec gates and goal tracking. No git operations — agents write code, you own the workflow.
argument-hint: <feature description>
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
model: opus
---

You are the top-level orchestrator. Turn $ARGUMENTS into working, reviewed, and documented code.

**No assumptions.** Verify actual state at every step. Never assume a file,
branch, task, or PR is in a particular state — always read and check first.

There are exactly FOUR points where you stop and wait for the human:
1. Drift/modify acknowledgement (Pre-flight PF4/PF3) — only when an existing feature is detected or drift is found.
2. Spec review (Phase 0a) — always, so the human can edit the spec.
3. Stack confirmation (Phase 0c) — only if preferences are not yet on file.
4. Plan approval (Phase 1) — always, before any build work starts.

After the human says "go" at Phase 1, everything runs automatically.
The human does not need to run any other command.
Agents do NOT touch git beyond read-only drift detection — no branching, no commits, no pushes, no PRs. That is the human's workflow.

---

## Pre-flight — Environment, drift detection, and feature routing

Run these checks BEFORE doing anything else. Do not skip them even if $ARGUMENTS seems clear.

### PF1 — Conflict state check

```bash
ls .git/MERGE_HEAD .git/REBASE_HEAD .git/CHERRY_PICK_HEAD .git/REVERT_HEAD 2>/dev/null
```

If any file exists: **STOP immediately.**
```
Branch is mid-<MERGE|REBASE|CHERRY-PICK|REVERT> (conflict state).
git ls-files -s returns stage 1/2/3 entries for conflicted files —
drift detection cannot run reliably.

Resolve or abort the operation first:
  git merge --abort  /  git rebase --abort  /  git cherry-pick --abort
Then re-run /plan.
```

Also verify no unresolved paths in the index:
```bash
git status --short | grep -cE "^(DD|AU|UD|UA|DU|AA|UU)" 2>/dev/null || echo 0
```
If count > 0: same stop message.

### PF2 — Scan existing features

```bash
ls -d .specify/*/ 2>/dev/null
```

For each feature directory found, read its one-line goal:
```bash
for dir in .specify/*/; do
  slug=$(basename "$dir")
  [ "$slug" = "current" ] && continue
  goal=$(grep -A1 "^## User goal" "$dir/goal.md" 2>/dev/null | tail -1 | xargs)
  echo "$slug: ${goal:-(no goal.md)}"
done
```

**Determine intent from $ARGUMENTS:**

- **Slug match** — if $ARGUMENTS starts with a slug that matches an existing `.specify/<slug>/` directory:
  Set `MODE=MODIFY`, `FEATURE_SLUG=<slug>`. Go to PF3.

- **Keyword overlap** — if keywords in $ARGUMENTS strongly match an existing feature's goal or spec title:
  Print:
  ```
  This looks related to an existing feature: <slug> — <goal>
    • Reply "modify" to extend that feature
    • Reply "new" to create a new separate feature
  ```
  **STOP** until answered. Set MODE accordingly.

- **No match**: Set `MODE=NEW`. Skip PF3 and PF4 (no existing feature to check). Go to Phase 0a.

### PF3 — Load existing feature state (MODE=MODIFY only)

Verify required files exist:
```bash
ls ".specify/$FEATURE_SLUG/spec.md" \
   ".specify/$FEATURE_SLUG/goal.md" \
   ".specify/$FEATURE_SLUG/plan.md" \
   ".specify/$FEATURE_SLUG/tasks.md" 2>/dev/null | wc -l
```
If not 4: report which files are missing. Ask human to restore them or switch to MODE=NEW.

Read tasks.md and goal.md. Build a state summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXISTING FEATURE: $FEATURE_SLUG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal: <from goal.md>

Tasks: <X done> · <Y blocked> · <Z pending>
Signals: <A>/<total> met

Done:    T001 — <title>, T002 — <title>
Blocked: T003 — <title> (<stop reason>)
Pending: T004 — <title>, T005 — <title>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What do you want to change?
  • "add: <requirement>" — extend the spec with new requirements
  • "fix: <TASK_ID> — <guidance>" — retry a blocked task with new guidance
  • "edit spec" — review and edit the spec before proceeding
  • "edit goal" — revise the user goal statement
  • "continue" — resume building the next pending task as-is
```

**STOP** until answered.

On "add: <requirement>": append requirement to spec.md, note it for PF4's drift check, proceed.
On "fix: <TASK_ID>": note the task ID and guidance. After PF4, route directly to Phase 2b for that task.
On "edit spec" or "edit goal": show the file, apply changes, re-show, STOP again.
On "continue": proceed to PF4 without spec changes.

After answer: set `FEATURE_SLUG` and write it to `.specify/current`. Skip Phase 0a (slug already set).

### PF4 — Drift detection

Run for the feature being modified (MODE=MODIFY) or any existing feature whose code
the new feature explicitly depends on (ask if needed).
Skip entirely if MODE=NEW and no dependency declared.

**Exclusion patterns (never flag these as drift):**
```
dist/  build/  out/  .next/  coverage/  __pycache__/
*.generated.*  *.pb.go  *_gen.go  *.min.js
package-lock.json  yarn.lock  poetry.lock  Pipfile.lock  go.sum
```
Also read `.gitignore` and add its entries to exclusions.

---

#### Tier 1 — Blob SHA batch check (zero LLM tokens)

Check for fingerprint:
```bash
ls ".specify/$FEATURE_SLUG/.fingerprint" 2>/dev/null || echo "NO_FINGERPRINT"
```
If NO_FINGERPRINT: skip Tier 1. Print `Drift check: no fingerprint (pre-fingerprint feature)`.

If fingerprint exists, extract all tracked paths:
```bash
grep -E "^\s+\S+: blob:" ".specify/$FEATURE_SLUG/.fingerprint" \
  | sed 's/^ *//' | cut -d: -f1
```

Batch check all paths in one call:
```bash
git ls-files -s <all paths from above> 2>/dev/null
```

For each entry in the fingerprint:

| Fingerprint says | Current state | Severity | Label |
|---|---|---|---|
| `not_yet_created` | File exists in index | INFO | "created outside agent loop" |
| `not_yet_created` | File absent | — | Skip (expected) |
| `blob:<SHA>` | File absent from index | HIGH | "file deleted" |
| `blob:<SHA>` | Current blob = fingerprinted blob | — | Clean, skip |
| `blob:<SHA>` | Current blob ≠ fingerprinted blob | Check below | |

For blob mismatch, before flagging HIGH — check if whitespace-only:
```bash
git diff <fingerprinted_blob>..<current_blob> -- <file> --ignore-all-space --ignore-blank-lines 2>/dev/null | wc -l
```
- If 0: flag **SKIP** (formatting only — not real drift)
- If > 0 AND file is `package.json` or matches lock file pattern: flag **LOW** (dependency update)
- If > 0 AND normal source file: flag **HIGH**

Also check spec files against their stored blobs:
```bash
grep "^spec_blob:\|^goal_blob:\|^tasks_blob:" ".specify/$FEATURE_SLUG/.fingerprint"
git ls-files -s ".specify/$FEATURE_SLUG/spec.md" ".specify/$FEATURE_SLUG/goal.md" ".specify/$FEATURE_SLUG/tasks.md"
```
If any spec-file blob differs from fingerprint: flag **INFO** ("spec/goal/tasks edited manually since plan was generated").

---

#### Tier 2 — New file scan (zero LLM tokens)

Find the commit that first added spec.md:
```bash
SPEC_COMMIT=$(git log --diff-filter=A --format="%H" -- ".specify/$FEATURE_SLUG/spec.md" | tail -1)
```

If SPEC_COMMIT is empty (file not yet committed): skip Tier 2.

Find source files added after spec creation, not in any SCOPE:
```bash
git log "${SPEC_COMMIT}..HEAD" --diff-filter=A --name-only --format="" \
  -- "${SOURCE_ROOT:-src}/" 2>/dev/null \
  | grep -vE "(dist/|build/|\.generated\.|\.pb\.go|_gen\.go|\.min\.js|node_modules)" \
  | sort -u
```

Cross-reference against all SCOPE paths in tasks.md:
```bash
grep "^\- \*\*Scope\*\*:" ".specify/$FEATURE_SLUG/tasks.md" \
  | sed 's/.*Scope\*\*: //' | tr ',' '\n' | xargs -I{} echo {} | sort -u
```

Files that appear in the git log but NOT in any SCOPE: flag **INFO** ("source file added outside agent loop").

---

#### Tier 3 — Semantic review (one LLM call, only if HIGH severity found)

If any HIGH-severity drift was detected, dispatch the reviewer with:
- The spec at `$SPEC_PATH`
- The diff of each HIGH-severity file:
  ```bash
  git show <fingerprinted_blob> 2>/dev/null > /tmp/drift_before.txt || echo "(new file)" > /tmp/drift_before.txt
  git show "HEAD:<file>" 2>/dev/null > /tmp/drift_after.txt || echo "(deleted)" > /tmp/drift_after.txt
  diff /tmp/drift_before.txt /tmp/drift_after.txt
  rm -f /tmp/drift_before.txt /tmp/drift_after.txt
  ```
- Question: "Does this change contradict the spec? Does it alter any API contract, data model, or interface that remaining planned tasks depend on?"

---

#### Drift report

If any drift was found (any severity), print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DRIFT REPORT — $FEATURE_SLUG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIGH  src/orders/routes.js — logic changed since plan (2 commits)
LOW   package.json — dependency update
INFO  src/payments/service.js — new file, not in any task SCOPE
INFO  spec.md — edited manually since plan was generated

Reviewer: <assessment from Tier 3 if run, else "(Tier 3 not triggered)">

  • "acknowledge" — accept these as the new baseline; fingerprint updated
  • "review: <file>" — show me the full diff for a specific file
  • "re-plan" — re-run the planner against the current spec/code state
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**STOP** until answered.

On "acknowledge": update `.specify/$FEATURE_SLUG/.fingerprint` — set each HIGH-severity file's entry to its current blob SHA. Stage the fingerprint. Continue.
On "review: <file>": show `git diff <fingerprinted_blob>..HEAD -- <file>`. Re-show drift report. STOP again.
On "re-plan": dispatch planner with current spec.md, regenerate plan.md and tasks.md. Then show plan for approval as in Phase 1.

If NO drift found at any tier: print `Drift check: clean` and continue silently without stopping.

---

## Phase 0 — Bootstrap spec and confirm stack

### 0a — Derive feature slug and create workspace

From $ARGUMENTS, derive a short kebab-case slug (2–3 meaningful words, no stop words):
- "Build auth API with JWT tokens" → `auth-api`
- "Order processing system with background jobs" → `order-processing`
- "User profile and settings page" → `user-profile`

```bash
FEATURE_SLUG="<derived slug>"
mkdir -p ".specify/$FEATURE_SLUG"
```

Verify the directory was created:
```bash
ls -d ".specify/$FEATURE_SLUG" 2>/dev/null || echo "MKDIR_FAILED"
```
If MKDIR_FAILED: stop and report the error.

Write $ARGUMENTS verbatim to `.specify/$FEATURE_SLUG/spec.md`.
Write the slug to `.specify/current`.

Verify both files exist before continuing:
```bash
ls ".specify/$FEATURE_SLUG/spec.md" ".specify/current" 2>/dev/null | wc -l
```
If not 2: stop and report which file failed to write.

### 0a' — Show spec and wait for human confirmation

Print the spec in full so the human can review it before anything else happens:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPEC DRAFT — $FEATURE_SLUG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<contents of .specify/$FEATURE_SLUG/spec.md>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Does this capture what you want to build?
  • Reply "confirmed" to proceed to stack selection
  • Reply "edit: <describe changes>" and I'll update the spec
  • Or edit .specify/$FEATURE_SLUG/spec.md directly and reply "ready"
```

**STOP — wait for human reply.**

On "edit: <changes>": update spec.md accordingly, re-print it in full, STOP again.
On "confirmed" or "ready": re-read spec.md to pick up any manual edits, then continue.

Also ask: **"What does success look like from a user's perspective?"**
One or two sentences describing what a user can actually _do_ when this feature
is complete. This becomes the feature goal that every agent keeps in view.

If the human included this in their original $ARGUMENTS or in "confirmed", extract it.
Otherwise ask explicitly and wait for an answer. Store the response as `USER_GOAL`.

### 0b — Check if shared stack preferences exist

Read `.specify/preferences.md`. If the file does not exist, go to 0c.

If it exists, check whether all ten required fields (`language`, `framework`,
`testing`, `database`, `auth`, `test_strategy`, `file_naming`, `folder_structure`,
`source_root`, `test_location`) have real values (not blank, not a `#` comment).

If **all ten are confirmed** → skip to Phase 1.

### 0c — Analyze spec and surface stack suggestions

Dispatch planner in suggestion mode:
- Pass the verified spec at `.specify/$FEATURE_SLUG/spec.md`
- Pass the output directory: `.specify/$FEATURE_SLUG/`

It analyzes the spec + existing repo structure and outputs a `NEEDS_INPUT` block
with specific recommended values and a one-line reason for each choice.

When the planner returns `NEEDS_INPUT`:

1. Print the block **exactly as returned** — do not paraphrase.
2. **STOP.** Tell the human:
   ```
   Reply "confirmed" to proceed with these, or tell me what to change
   (e.g. "use FastAPI", "PostgreSQL not in-memory", "no auth needed").
   ```

Do NOT proceed to Phase 1 until the human replies.

### 0d — Write confirmed preferences and bootstrap constitution

When the human replies:

1. Apply any changes requested.
2. Write `.specify/preferences.md`:
```
# Confirmed stack preferences — shared across features

language:           <confirmed value>
framework:          <confirmed value>
testing:            <confirmed value>
linting:            <confirmed value or blank>
package_manager:    <inferred or blank>

database:           <confirmed value>
auth:               <confirmed value>
deployment_target:  local only

api_style:          <inferred from spec or blank>

# test_strategy: unit        = mock all external deps (fast, no infra)
#                integration = real test DB/services per test
#                both        = unit tests for logic + one integration test per major flow
test_strategy: both

# ── Naming & folder conventions ──────────────────────────────────────────────
# These apply to every file and folder agents create. Never deviate.

# file_naming: how source files are named
#   kebab-case  → user-routes.js, order-service.py
#   snake_case  → user_routes.js, order_service.py
#   camelCase   → userRoutes.js, orderService.js
#   PascalCase  → UserRoutes.ts, OrderService.ts
file_naming:        <confirmed value>

# folder_structure: how the source tree is organised
#   feature-based → src/orders/, src/users/, src/auth/
#   layer-based   → src/controllers/, src/services/, src/repositories/
#   flat          → src/ (everything at one level)
folder_structure:   <confirmed value>

# source_root: top-level directory for all application code
source_root:        <confirmed value>   # e.g. src, app, lib, cmd

# test_location: where test files live relative to source
#   colocated → <module>.test.js sits next to <module>.js
#   tests/    → tests/ mirrors src/ structure
#   __tests__ → __tests__/ at project root (Jest default)
test_location:      <confirmed value>

# variable_naming: local variables and function parameters
variable_naming:    <camelCase | snake_case>

# class_naming: classes, interfaces, types, components
class_naming:       PascalCase

# constant_naming: exported constants and env-backed values
constant_naming:    UPPER_SNAKE_CASE

# api_routes: URL path segment casing
api_routes:         </kebab-case | /camelCase | /snake_case>

# db_naming: table names and column names
db_naming:          <snake_case | camelCase>

# commit_strategy: ask  = prompt to stage + commit after each task (recommended)
#                  auto = stage + commit automatically after each task
#                  off  = never touch git (commit manually)
commit_strategy:    ask

# branch_strategy: auto   = create feat/<TASK_ID>-<title> branch if on main/master/develop/trunk
#                  manual = you create and switch branches yourself
branch_strategy:    auto
# ─────────────────────────────────────────────────────────────────────────────
```
Verify the file was written by reading it back.

3. If `.specify/constitution.md` does not already exist:

Parse OWNER and REPO from git remote — this is the same for every user on the repo:
```bash
REMOTE=$(git remote get-url origin 2>/dev/null || echo "UNKNOWN")
```
- HTTPS: `https://github.com/OWNER/REPO.git` → strip prefix and `.git`
- SSH: `git@github.com:OWNER/REPO.git` → strip prefix and `.git`
- If UNKNOWN or parse fails: use `unknown/unknown`.

Write `.specify/constitution.md`:
```markdown
# Project Constitution

repo: <OWNER/REPO or unknown/unknown>
project_number: none
default_milestone: mvp

## Labels
in-progress:   FBCA04
needs-review:  0075CA
done:          0E8A16
blocked:       D93F0B
```
Verify the file was written.

---

## Phase 1 — Generate and confirm the plan

**Verify before dispatching planner:**
```bash
ls ".specify/$FEATURE_SLUG/spec.md" ".specify/preferences.md" 2>/dev/null | wc -l
```
If not 2: stop — tell the human which file is missing and how to fix it.

Dispatch planner with:
- Spec at `.specify/$FEATURE_SLUG/spec.md`
- Preferences at `.specify/preferences.md`
- Output directory: `.specify/$FEATURE_SLUG/`

The planner writes `.specify/$FEATURE_SLUG/plan.md` and
`.specify/$FEATURE_SLUG/tasks.md`, then prints `PLAN COMPLETE`.

If planner outputs `NEEDS_INPUT` again: relay to human and STOP.

**Verify planner output before committing:**
```bash
ls ".specify/$FEATURE_SLUG/goal.md" \
   ".specify/$FEATURE_SLUG/plan.md" \
   ".specify/$FEATURE_SLUG/tasks.md" 2>/dev/null | wc -l
```
If not 3: stop — "Planner did not write expected files. Check planner output above."

Read `.specify/$FEATURE_SLUG/goal.md`, `.specify/$FEATURE_SLUG/plan.md`,
and `.specify/$FEATURE_SLUG/tasks.md`.

Print the full plan:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PLAN READY — <feature title>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal: <user goal from goal.md>

Stack: <stack line from plan.md>

Phase 1 — <name> (<milestone-slug>)
  Goal: <goal line>
  Signals: <S1, S2>
  T001 — <title>  [spec req: <R> · signals: <SX>]
  T002 — <title>  [spec req: <R> · signals: <SX>]
  ...

Phase 2 — <name> (<milestone-slug>)
  Goal: <goal line>
  Signals: <S3>
  T003 — <title>  [spec req: <R> · signals: <SX>]
  ...

<N> phases · <M> tasks total
Goal signals: <total count>
Spec: .specify/$FEATURE_SLUG/spec.md

Once you reply "go", I will build all phases automatically — branches,
tasks, GitHub issues, spec and goal gates, and PRs. No further commands needed.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Reply "go" to start, or tell me what to change first
(e.g. "split T003 into two tasks", "add a caching requirement to spec",
"update the goal statement").
```

**STOP — wait for human to reply.**

If the human requests task changes: apply directly to `tasks.md`, re-print.
If the human requests spec changes: update `spec.md`, re-dispatch planner, re-print.
Stop again each time until the human says "go".

---

## Phase 2 — Per-phase build loop (fully automatic after "go")

**Verify required files exist before starting any build work:**
```bash
ls ".specify/$FEATURE_SLUG/spec.md" \
   ".specify/$FEATURE_SLUG/plan.md" \
   ".specify/$FEATURE_SLUG/tasks.md" \
   ".specify/preferences.md" \
   ".specify/constitution.md" 2>/dev/null | wc -l
```
If not 5: stop — list which files are missing. Do not proceed.

Set:
- `SPEC_PATH = ".specify/$FEATURE_SLUG/spec.md"`
- `GOAL_PATH = ".specify/$FEATURE_SLUG/goal.md"`
- `TASKS_PATH = ".specify/$FEATURE_SLUG/tasks.md"`
- `PLAN_PATH = ".specify/$FEATURE_SLUG/plan.md"`
- `test_strategy` = read from `.specify/preferences.md` (default: `both`)

Read `$PLAN_PATH` to identify all phases and which tasks belong to each.

For EACH phase:

### 2a — Begin phase

Print: `[Phase N] Building: <phase name> (<milestone-slug>)`

Re-read `$TASKS_PATH` fresh to get the current task list for this phase.

### 2b — Build all tasks in this phase

Re-read `$TASKS_PATH` fresh — do not rely on any prior read.

Initialise:
- `phase_completed = []`
- `phase_blocked = []`
- `phase_issues = []`

For each task in this phase (in order):

1. Re-read `$TASKS_PATH` to get the current status of this task. If the task is
   already `[x]`, skip it (was completed in a prior run). If `[~]`, note it as
   still blocked and skip.

2. Extract TASK_ID, TASK_TITLE, MILESTONE, SPEC_REQ, SCOPE, DONE_WHEN.

3. Dispatch tracker: `CREATE_ISSUE title="<TASK_ID>: <TASK_TITLE>" milestone="<MILESTONE>" body="<task brief>"`
   Capture ISSUE_NUM or "N/A".

4. Run the build loop (up to 5 cycles):
   - Dispatch builder with task brief + `$SPEC_PATH` + preferences.md + failure history.
   - Dispatch checker.
   - If INFRA_FAILURE: stop the loop immediately. Do not retry — the builder cannot fix environment issues. Escalate to the human with the checker's error line and instructions to fix the environment (start Docker, set DB connection string, install missing tool).
   - If FAILED: check stop conditions; if not stopped, feed failure history back.
   - If ALL GREEN: tracker `UPDATE_LABEL` (in-progress → needs-review); dispatch reviewer
     with task brief + `$SPEC_PATH`.
   - If APPROVED:
     - Mark `[x]` in `$TASKS_PATH`; verify by re-reading that line.
     - Dispatch docs-writer with task brief + diff context so it can update README/ARCHITECTURE.
     - Update fingerprint for this task's SCOPE files:
       For each file in SCOPE that now exists in the working tree:
       ```bash
       blob=$(git ls-files -s <file> 2>/dev/null | awk '{print $2}')
       [ -n "$blob" ] && sed -i "s|$(printf '%s\n' "<file>" | sed 's/[[\.*^$()+?{|]/\\&/g'): not_yet_created|$(printf '%s\n' "<file>" | sed 's/[[\.*^$()+?{|]/\\&/g'): blob:$blob|" ".specify/$FEATURE_SLUG/.fingerprint" 2>/dev/null
       ```
     - Print: `[TASK_ID done] <TASK_TITLE> — files: <SCOPE file list>`
     - Append to phase_completed; tracker `CLOSE_DONE`.
     - Run commit flow (see § Commit flow below).
   - If BLOCKED: escalate (see below); mark `[~]`; append to phase_blocked;
     tracker `CLOSE_BLOCKED`; **continue to next task**.

5. Print running scoreboard after each task:
   ```
   [Phase N] Progress: X done, Y blocked, Z remaining
   ```

### § Commit flow (shared by 2b and speckit-loop)

Read `commit_strategy` from `.specify/preferences.md` (default `ask` if absent).
Read `branch_strategy` from `.specify/preferences.md` (default `auto` if absent).
Never default to `off` for either — that silently regresses existing projects.

**If `commit_strategy: off`**: print files that need manual staging and skip all steps below.
```
Files ready to commit manually:
  <SCOPE files>
  .specify/<FEATURE_SLUG>/tasks.md
  .specify/<FEATURE_SLUG>/.fingerprint
```

**Otherwise (ask or auto), run these steps in order:**

**Step 1 — Pull**
```bash
git diff --cached --quiet || git restore --staged .
BRANCH=$(git branch --show-current)
git pull --rebase origin "$BRANCH" 2>&1
```
If non-zero exit: **STOP** — "Pull failed — resolve conflicts first, then re-run."

**Step 2 — Branch (if branch_strategy: auto)**
If `BRANCH` is `main`, `master`, `develop`, or `trunk`:
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
If already on a feature branch: commit to it as-is.

**Step 3 — Stage SCOPE files**
```bash
git add <SCOPE files>
```

**Step 4 — Update fingerprint** (now git ls-files -s returns real SHAs for staged files)
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

Always stage only the explicit SCOPE file list + tasks.md + .fingerprint. Never use `git add .` or `git add -A`.

---

### 2c — Spec gate and goal progress check

Re-read `$SPEC_PATH` and `$GOAL_PATH` fresh before dispatching reviewer.

Dispatch reviewer with:
- All requirements from `$SPEC_PATH` (re-read)
- User goal and success signals from `$GOAL_PATH` (re-read)
- All SCOPE files created or modified by tasks in this phase (from phase_completed list)
- Spec requirements and goal signals this phase was supposed to advance (from `$PLAN_PATH`)

Ask: "Does this phase fully deliver its stated spec requirements AND advance its
declared goal signals?"

If PARTIAL or MISSING (spec):
1. Report missing requirements to human.
2. Generate gap-filling tasks; run them through the build loop.
3. Re-run spec gate.
4. If still failing after one retry: STOP and escalate to human.

After spec gate passes — **update goal progress:**

Re-read `$GOAL_PATH`. For each success signal this phase was supposed to advance,
mark it `[x]` if the phase's code makes it demonstrable. Leave signals `[ ]` if
the code does not yet enable them.

Update the `## Goal progress` section in `$GOAL_PATH`:
```
Phase N — <name>: <signals advanced: S1 ✓, S2 ✓> | <signals still pending: S3>
```

Update goal.md on disk — the user will commit it with the rest of their work.

Print:
```
[Phase N goal check]
Signals advanced this phase: <S1 ✓, S2 ✓>
Signals still pending:       <S3, S4>
Overall: <X>/<total> signals complete
```

If all signals are now `[x]`: note "USER GOAL REACHED" — still continue to Phase 3 report.

### 2d — Phase complete

Print:
```
[Phase N complete] <phase name>
  Tasks done:    <X>
  Tasks blocked: <Y>
  Files changed: <list of all SCOPE files from phase_completed tasks>
  Signals advanced: <S1 ✓, S2 ✓>
```

Commit, branch, and PR are yours to create on your own schedule.

---

## Escalation format (for blocked tasks)

```
🚨 BLOCKED — <TASK_ID>: <TASK_TITLE>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Spec requirement: <SPEC_REQ>
Stop reason: <which condition>
Cycles tried: <N>

What was attempted:
<failure log summary>

What I need from you:
<specific question with options if applicable>

GitHub issue #<N> labelled 'blocked'. Pipeline continuing with next task.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Phase 3 — Final pipeline report

Re-read `$GOAL_PATH` fresh.

```
============================================================
PIPELINE COMPLETE — <feature title>

Goal    : <user goal from goal.md>
Spec    : .specify/$FEATURE_SLUG/spec.md

Phase 1 — <name>
  Tasks     : X done · Y blocked
  Spec gate : APPROVED / PARTIAL
  Signals   : S1 ✓, S2 ✓

Phase 2 — <name>
  Tasks     : X done · Y blocked
  Spec gate : APPROVED / PARTIAL
  Signals   : S3 ✓

Goal signals:
  S1: <description> ✓
  S2: <description> ✓
  S3: <description> ✗ (pending)

Files ready for your review:
  <all SCOPE files from all completed tasks, grouped by phase>

Blocked tasks (need your attention):
  🚨 TXXX — title — stop reason — #issue

Total: <X> tasks done, <Y> blocked across <N> phases
Goal : <X>/<total> signals complete

Next steps (yours to do):
  - Review the files listed above
  - Commit, branch, and push on your schedule
  - For blocked tasks: /speckit-loop $FEATURE_SLUG
============================================================
```

**If any success signals are still `[ ]` (not yet reachable from built code):**

Note in the report:
```
⚠️  GOAL NOT FULLY MET

These signals are still pending:
  S3: <description> — no task covered this yet
```

---

## Stop conditions (CLAUDE.md — per task, not per pipeline)
A blocked task does NOT stop the pipeline. The next task starts immediately.
Never weaken a check. Never report success without checker output.
