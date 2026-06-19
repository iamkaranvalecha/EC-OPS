---
description: Resume an interrupted session — shows current feature state, uncommitted work, and the next pending task, then hands off to speckit-loop.
argument-hint: [feature-slug] (optional — reads .specify/current if omitted)
allowed-tools: Read, Bash, Glob, Task
model: sonnet
---

You orient, you do not build. Show the human exactly where they left off, then hand off to speckit-loop.

## Step 1 — Conflict check

```bash
ls .git/MERGE_HEAD .git/REBASE_HEAD .git/CHERRY_PICK_HEAD .git/REVERT_HEAD 2>/dev/null
```

If any file exists: **STOP.**
```
Branch is in conflict state. Resolve or abort first:
  git merge --abort  /  git rebase --abort  /  git cherry-pick --abort
Then re-run /resume.
```

## Step 2 — Resolve feature

If `$ARGUMENTS` is non-empty and matches an existing `.specify/<slug>/` directory:
use that slug as FEATURE_SLUG.

Otherwise:
```bash
cat .specify/current 2>/dev/null
```
If the slug exists and `.specify/<slug>/` is a real directory: use it.

If `.specify/current` is missing or points to a non-existent directory:
```bash
ls -d .specify/*/ 2>/dev/null
```
- Exactly one result → use it; note: "Using the only feature found: `<slug>`"
- Multiple results → print the list and ask which to resume. **STOP** until answered.
- None → **STOP**: "No features found. Run /plan <description> to start one."

## Step 3 — Read feature state

Verify required files exist:
```bash
ls ".specify/$FEATURE_SLUG/goal.md" ".specify/$FEATURE_SLUG/tasks.md" 2>/dev/null | wc -l
```
If not 2: **STOP** — report which file is missing and suggest re-running `/plan`.

Read `goal.md`: extract the text under `## User goal` (one to two sentences).

Read `tasks.md`: count status markers:
- `DONE_COUNT`    = number of `[x]` lines
- `PENDING_COUNT` = number of `[ ]` lines
- `BLOCKED_COUNT` = number of `[~]` lines

Find the first `[ ]` task: extract its `## TXXX —` heading for ID and title.
If no `[ ]` task exists: set NEXT_TASK to "(none — all tasks complete or blocked)".

## Step 4 — Uncommitted files

```bash
git status --short 2>/dev/null | grep -vE "^.. (\.specify/|\.claude/)"
```

Capture as UNCOMMITTED_FILES. If empty: set to "(none)".

## Step 5 — Print summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESUMING: <FEATURE_SLUG>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal: <user goal from goal.md>

Tasks: <DONE_COUNT> done · <PENDING_COUNT> pending · <BLOCKED_COUNT> blocked
Next:  <TASK_ID> — <TASK_TITLE>

Uncommitted files:
  <UNCOMMITTED_FILES — each line indented two spaces, or "(none)">
<if UNCOMMITTED_FILES is non-empty: "  ^ from your last session — commit when ready">
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Continue? (yes / show task details / list all tasks)
```

**STOP** and wait for the human to reply.

## Step 6 — Handle response

**"yes"**
Dispatch speckit-loop with no arguments. It will read `.specify/current` and pick up the next `[ ]` task automatically.

**"show task details"**
Re-read `tasks.md`. Print the full task block for the first `[ ]` task (all fields: Status, Phase, Milestone, Spec requirement, Goal signals, Scope, Done when). Ask:
```
Continue? (yes / list all tasks)
```
**STOP** again. On "yes" → dispatch speckit-loop.

**"list all tasks"**
Re-read `tasks.md`. Print one line per task:
```
[x] T001 — <title>
[ ] T002 — <title>
[~] T003 — <title> (blocked)
```
Ask:
```
Continue? (yes)
```
**STOP** again. On "yes" → dispatch speckit-loop.

**Any other reply**
Treat as guidance for the next task and pass it through to speckit-loop as `$ARGUMENTS`.
