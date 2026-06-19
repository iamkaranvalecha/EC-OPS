# AgentTeams

## Loop stop rules

The team loops until one of these is true:

- ALL GREEN: every check passes. Stop and report success with proof.
- 5 cycles used: stop. Report what still fails and what was tried.
- Same failure twice in a row: stop. The builder is guessing, not
  fixing. Escalate to me.
- A fix makes a previously passing check fail: stop. Something is
  being broken to fix something else.

Never report success without checker output from the final cycle.
Never weaken or delete a check to reach ALL GREEN.

## No assumptions — verify everything

Every agent and command must verify actual state before acting.
Never assume a file, branch, task, or PR is in a particular state
because a previous step said it would be. Verify it.

Specific rules:
- Before reading a file: verify it exists. If it doesn't, stop and
  report what's missing — do not proceed with defaults or guesses.
- Before git operations: run `git status` and confirm the working tree
  state. Never assume it's clean or on the expected branch.
- Before branching: check `git branch --list <name>`. If the branch
  already exists, ask the human what to do — do not overwrite it.
- Before running test/lint/type commands: verify the config file
  (package.json, pyproject.toml, go.mod, Cargo.toml) exists and
  contains the expected script. Do not run a command that isn't there.
- Before tracker operations: verify .specify/constitution.md exists
  and contains repo/owner fields. If missing, report and skip — do
  not fail the whole pipeline.
- After every git commit/push/merge: check the exit code and confirm
  the operation actually completed. Do not assume success.
- When resuming work: re-read every file you need. Never carry over
  state from a previous session — the human may have edited anything.
