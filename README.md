# Hermes Workspace

Workspace and SSH-first ops hub for managing remote Hermes Agent targets.

It gives each remote Hermes Agent a git-backed work management repository, preserves task and research artifacts, checks whether Hermes is online, initializes Kanban, restarts the gateway, and inspects Discord thread work from logs. Target profiles keep macOS-specific operations, Linux examples, and future hosts out of the command code.

## Quick Start

Agent/Claude operators should read `AGENTS.md` first. This repo has two roles:

- **Control-side remote ops**: run `bin/hermes-remote` from the Control MacBook to inspect or operate a configured Hermes target.
- **Hermes-side workspace work**: let the remote Hermes agent use this repo as its default working directory for tasks, reports, and research artifacts.

### Control-Side Remote Ops

```bash
cp config/example.env .env
bin/hermes-remote --target bobeen-mac config
bin/hermes-remote --target bobeen-mac check-ssh
bin/hermes-remote --target bobeen-mac status
```

Target profiles live under `config/targets/`. The default target is `bobeen-mac`, which expects this local SSH alias:

```sshconfig
Host bobeen
  HostName 100.89.89.70
  User bobeenlee
  IdentityFile ~/.ssh/id_ed25519_bobeenlee_nopass
  IdentitiesOnly yes
```

### Hermes-Side Workspace

The canonical remote workspace for the default macOS target is:

```text
/Users/bobeenlee/Workspaces/hermes-workspace
```

Hermes should use this config shape:

```yaml
terminal:
  cwd: "/Users/bobeenlee/Workspaces/hermes-workspace"

worktree: true
```

For another target, set `terminal.cwd` to that profile's `HERMES_WORKSPACE_ROOT`.

## Target Profiles

Use `--target <name>` or `HERMES_TARGET=<name>` to select a target profile:

```bash
bin/hermes-remote --target bobeen-mac status
HERMES_TARGET=bobeen-mac bin/hermes-remote config
```

Profile files are ordinary shell env files:

```text
config/targets/bobeen-mac.env
config/targets/linux-example.env
```

Each profile defines the SSH host, remote home, OS, service manager, computer-use backend, Hermes config path, and workspace root. Local `.env` is optional and only overrides the selected profile on the current control machine.

## GitHub Pages

The landing page source lives under `pages/` on `main`:

```text
pages/index.html
pages/styles/main.css
```

The published GitHub Pages branch is `gh-pages` from `/`, where the same static files are served as root `index.html` and `styles/main.css`.

## Remote Ops Commands

```bash
# Full status: gateway, optional computer_use, Kanban, dashboard, processes.
bin/hermes-remote status

# Install and wire Hermes computer_use on a macOS/cua-driver target.
bin/hermes-remote setup-computer-use

# Ask macOS to grant CuaDriver Accessibility + Screen Recording.
# This opens the permission flow on the remote macOS target and waits.
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

All Hermes-side workspace tasks should pass through the Workspace Lifecycle module documented in [docs/workspace-lifecycle.md](docs/workspace-lifecycle.md).

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
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-*`.
- The script reads remote paths from `config/targets/<target>.env`; use `.env` only for local overrides.
- CuaDriver-based `computer_use` commands are macOS target operations. Linux targets should use `HERMES_COMPUTER_USE_BACKEND=none` unless a supported backend is added.
