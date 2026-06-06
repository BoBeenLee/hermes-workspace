# Hermes Remote Ops

Small operator repo for managing a Hermes Agent on a remote Mac over SSH/Tailscale.

It is designed for the workflow used with `bobeen-macbookpro-2`: check whether Hermes is online, install/verify `computer_use`, initialize Kanban, restart the gateway, and inspect Discord thread work from logs.

## Quick Start

Agent/Claude operators should read `AGENTS.md` first. `CLAUDE.md` points Claude-style agents to the same guide.

```bash
cp config/example.env .env
bin/hermes-remote check-ssh
bin/hermes-remote status
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

## Notes

- The repo does not store SSH keys, provider keys, Discord tokens, or Hermes secrets.
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-remote-ops-*`.
- The script assumes the remote Hermes wrapper is at `/Users/bobeenlee/.local/bin/hermes`; change `.env` for another Mac.
