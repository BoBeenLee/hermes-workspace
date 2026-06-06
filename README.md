# Hermes Remote Ops

Small operator workspace for managing Hermes Agent installations on remote Macs over SSH/Tailscale.

It is designed for the workflow used with `bobeen-macbookpro-2`: check whether Hermes is online, install/verify `computer_use`, initialize Kanban, restart the gateway, and inspect Discord thread work from logs.

## Layout

```text
bin/                         stable command wrappers
packages/hermes-remote-cli/  reusable CLI package
projects/                    one non-secret env profile per Hermes target
repos/                       optional per-project notes or checkout inventory
docs/                        operational references
```

Use `projects/*.env` for each remote Hermes target. Use `repos/` for project-specific notes when several app/site repos are operated through the same remote Hermes agent.

The workspace also has a tiny `package.json` so more packages can be added under `packages/*` later without changing the top-level command shape.

## Quick Start

Agent/Claude operators should read `AGENTS.md` first. `CLAUDE.md` points Claude-style agents to the same guide.

```bash
cp config/example.env .env
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Or select a project profile explicitly:

```bash
bin/hermes-remote --project bobeen status
bin/hermes-remote --project bobeen is-working 1512384300689916064
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

# List project profiles and show active config.
bin/hermes-remote projects
bin/hermes-remote --project bobeen config

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

## Notes

- The repo does not store SSH keys, provider keys, Discord tokens, or Hermes secrets.
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-remote-ops-*`.
- The script assumes the remote Hermes wrapper is at `/Users/bobeenlee/.local/bin/hermes`; change `.env` for another Mac.
