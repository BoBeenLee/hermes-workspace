# Hermes Workspace

Operator repo for managing a Hermes Agent on a remote Mac over SSH/Tailscale.

It supports the `bobeen-macbookpro-2` flow: check Hermes, install/verify `computer_use`, initialize Kanban, restart gateway, inspect Discord thread work, and keep tasks inside a git-backed workspace lifecycle.

It also records the DGX Spark / AI TOP ATOM remote access path for `bobeenlee`, including SSH, DGX Dashboard tunneling, RDP/xrdp setup, and Chromium-on-arm64 notes. See [docs/dgx-spark-remote-access.md](docs/dgx-spark-remote-access.md).

Discord requests that are ambiguous or risky pass through a human-in-the-loop clarification gate before execution. Hermes uses the external mattpocock `grill-me` skill for one-question-at-a-time clarification, then waits for an Approval Summary to be approved in the Discord thread.

## Quick Start

Agent/Claude operators should read `AGENTS.md` first. `CLAUDE.md` points Claude-style agents to the same guide.

```bash
cp config/example.env .env
bin/hermes-remote check-ssh
bin/hermes-remote status
```

The canonical remote workspace for Hermes work is:

```text
/Users/bobeenlee/Workspaces/hermes-workspace
```

Hermes should use this config shape:

```yaml
terminal:
  cwd: "/Users/bobeenlee/Workspaces/hermes-workspace"

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
bin/hermes-remote status
bin/hermes-remote setup-computer-use
bin/hermes-remote grant-computer-use
bin/hermes-remote verify-computer-use
bin/hermes-remote setup-kanban
bin/hermes-remote antigravity-check
bin/hermes-remote gateway-restart
bin/hermes-remote is-working 1512384300689916064
bin/hermes-remote tail-thread 1512384300689916064
bin/hermes-remote run "Use computer_use to report two visible apps."
```

See `bin/hermes-remote help` for full CLI surface. Antigravity setup, auth, run, MCP worker, and collect commands are documented in [docs/antigravity-delegation.md](docs/antigravity-delegation.md).

DGX Spark access is documented separately in [docs/dgx-spark-remote-access.md](docs/dgx-spark-remote-access.md). Start there when the user asks about `aitopatom-36a9`, `172.30.1.87`, DGX Dashboard, RDP, xrdp, or Chromium on the DGX Spark.

## Workspace Lifecycle

All Hermes tasks should pass through the Workspace Lifecycle module documented in [docs/workspace-lifecycle.md](docs/workspace-lifecycle.md).

Task types:

- `ops-change`
- `remote-config`
- `incident-triage`
- `market-research`
- `analysis-report`
- `delegated-implementation`

Each task leaves a completion note with the branch/worktree, changed files or report path, tests/checks, source ledger when research-based, and completion mode: `done` or `review-required`.

Antigravity delegated implementation uses [docs/antigravity-delegation.md](docs/antigravity-delegation.md). Hermes stays supervisor; completion is `review-required`.

Discord HIL clarification is documented in [docs/discord-thread-triage.md](docs/discord-thread-triage.md). The remote Hermes profile should have `grill-me` installed from `mattpocock/skills`:

```bash
npx -y skills@latest add https://github.com/mattpocock/skills --skill grill-me --yes --global
```

Market research and analysis tasks use the Research Analysis module in [docs/research-workflow.md](docs/research-workflow.md). Research-based work writes briefs, source ledgers, notes, and reports under:

```text
research/
reports/
```

## Notes

- The repo does not store SSH keys, provider keys, Discord tokens, or Hermes secrets.
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-remote-ops-*`.
- The script assumes the remote Hermes wrapper is at `/Users/bobeenlee/.local/bin/hermes`; change `.env` for another Mac.
