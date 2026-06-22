# Antigravity Delegation

Antigravity delegated implementation lets Hermes call Antigravity CLI as an implementation worker on the active Hermes host. Hermes remains the supervisor and verifier.

## Operating Model

- Hermes starts from the active target profile's canonical remote workspace, `HERMES_REMOTE_WORKSPACE`.
- `bin/hermes-remote antigravity-run` creates an isolated git worktree and branch.
- v2 registers `antigravity-worker` as a Hermes MCP stdio server.
- The MCP worker creates an isolated git worktree and branch, then runs Antigravity CLI as a repo-local implementation worker.
- The MCP worker defaults to the Hermes workspace, but standalone product repos must pass an explicit `workspace` argument such as `<HERMES_REMOTE_HOME>/Workspaces/Todo`.
- Hermes must verify the returned `workspace` and `gitRoot` before treating delegated output as relevant to the requested repo.
- The default MCP execution mode is `print`, because it is non-interactive and avoids first-run TUI setup screens. `tmux` remains available for manual v1 sessions and explicit MCP requests.
- Session names follow `antigravity-<YYYYMMDD-HHMMSS>-<slug>`.
- Session artifacts are stored under `artifacts/antigravity/<session>/`.
- Completion mode is always `review-required`.

This v2 flow adds Skill and MCP tool integration only. It does not add Discord commands, gateway dispatch, or Kanban automatic routing.

## Commands

```bash
bin/hermes-remote antigravity-check
bin/hermes-remote setup-antigravity
bin/hermes-remote antigravity-auth
bin/hermes-remote antigravity-run "Implement the requested change and run checks."
bin/hermes-remote antigravity-status <session>
bin/hermes-remote antigravity-stop <session>
bin/hermes-remote antigravity-collect <session>
bin/hermes-remote setup-antigravity-worker
bin/hermes-remote verify-antigravity-worker
```

Hermes MCP tools exposed by `antigravity-worker`:

- `antigravity_check(workspace?)`
- `antigravity_start_task(task, mode?, workspace?)`
- `antigravity_status(session)`
- `antigravity_stop(session)`
- `antigravity_collect(session)`

## Setup And Auth

`setup-antigravity` installs or locates the `agy` binary on the remote Hermes host. `antigravity-auth` prints the SSH browser-code authentication steps. Authentication is a human step because Antigravity may print an authorization URL that must be opened in a local browser.

Do not copy provider tokens, `~/.hermes/auth.json`, SSH keys, `.env`, or other secret files into logs or reports.

## Supervision Rules

- Antigravity is allowed to implement only inside the isolated worktree.
- For standalone repos, Hermes must create or clone the target repo workspace first, then pass that workspace path to `antigravity_start_task`.
- Hermes verifies the final git diff and checks independently.
- Automatic approval is allowed only for repo-local implementation and verification commands.
- Destructive commands, remote config/auth changes, launchd changes, and gateway restarts require human review.
- `antigravity-collect` writes a completion note and never stages, commits, merges, or deploys files.

## Required Completion Evidence

Every delegated implementation must leave:

- task type: `delegated-implementation`
- Antigravity session id
- target workspace and git root
- branch and worktree path
- changed files or report path
- tests/checks run
- captured log path
- completion mode: `review-required`

Use `antigravity-collect <session>` to capture tmux output, git status, diff summary, full diff, and the completion note.

For MCP delegated work, use `antigravity_collect` to capture the same evidence. The worker returns only secret-safe summaries and artifact paths.
