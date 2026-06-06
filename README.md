# Hermes Remote Ops

Operator repo for managing a Hermes Agent on a remote Mac over SSH/Tailscale.

It is designed for the workflow used with `bobeen-macbookpro-2`: check whether Hermes is online, install/verify `computer_use`, initialize Kanban, restart the gateway, inspect Discord thread work from logs, and keep Hermes work inside a git-backed workspace lifecycle.

## Quick Start

Agent/Claude operators should read `AGENTS.md` first. `CLAUDE.md` points Claude-style agents to the same guide.

```bash
cp config/example.env .env
bin/hermes-remote check-ssh
bin/hermes-remote status
```

The canonical remote workspace for Hermes work is:

```text
/Users/bobeenlee/Workspaces/hermes-remote-ops
```

Hermes should use this config shape:

```yaml
terminal:
  cwd: "/Users/bobeenlee/Workspaces/hermes-remote-ops"

worktree: true
```

Default config expects this local SSH alias:

```sshconfig
Host bobeen
  HostName 100.89.89.70
  User bobeenlee
  IdentityFile ~/.ssh/id_ed25519_bobeenlee_nopass
  IdentitiesOnly yes
```

## Common Commands

```bash
# Full status: gateway, computer_use, Kanban, dashboard, processes.
bin/hermes-remote status

# Install and wire Hermes computer_use on the remote Mac.
bin/hermes-remote setup-computer-use

# Ask macOS to grant CuaDriver Accessibility + Screen Recording.
# This opens the permission flow on the remote Mac and waits.
bin/hermes-remote grant-computer-use

# Verify CuaDriver permissions, MCP tools, and screen/window access.
bin/hermes-remote verify-computer-use

# Initialize/check Kanban.
bin/hermes-remote setup-kanban

# Restart Hermes gateway after config changes.
bin/hermes-remote gateway-restart

# Check whether a Discord thread is currently active.
bin/hermes-remote is-working 1512384300689916064

# Tail recent gateway/agent lines for a Discord thread ID.
bin/hermes-remote tail-thread 1512384300689916064

# Run a one-shot Hermes prompt remotely.
bin/hermes-remote run "Use computer_use to report two visible apps."
```

## Workspace Lifecycle

All Hermes tasks should pass through the Workspace Lifecycle module documented in [docs/workspace-lifecycle.md](docs/workspace-lifecycle.md).

Task types:

- `ops-change`
- `remote-config`
- `incident-triage`
- `market-research`
- `analysis-report`

Each task leaves a completion note with the branch/worktree, changed files or report path, tests/checks, source ledger when research-based, and completion mode: `done` or `review-required`.

Market research and analysis tasks use the Research Analysis module in [docs/research-workflow.md](docs/research-workflow.md). Research-based work writes briefs, source ledgers, notes, and reports under:

```text
research/
reports/
```

## Notes

- The repo does not store SSH keys, provider keys, Discord tokens, or Hermes secrets.
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-remote-ops-*`.
- The script assumes the remote Hermes wrapper is at `/Users/bobeenlee/.local/bin/hermes`; change `.env` for another Mac.
