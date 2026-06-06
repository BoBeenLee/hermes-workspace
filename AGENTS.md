# Hermes Remote Ops Agent Guide

This directory contains a small SSH-first operations toolkit for managing the remote Hermes Agent running on the Hermes MacBook.

Use this guide before changing files in `hermes-remote-ops/` or operating the remote Mac.

## Source Context

The operating model comes from:

- `../docs/plans/36-macbook-remote-hermes-agent.md`
- `../docs/hermes-agent.md`
- `../CONTEXT.md`

Important language from the plan:

- **Control MacBook**: the local Mac where Codex/Desktop automation runs.
- **Hermes MacBook**: the remote Mac that runs NousResearch `hermes-agent`.
- **Hermes agent**: the per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.
- **Remote access path**: SSH key access from Control MacBook to Hermes MacBook. Tailscale/LAN aliases are access paths, not application state.

## Current Default Target

Default values live in `config/example.env` and can be overridden by a local `.env`.

- SSH alias: `bobeen`
- Remote user: `bobeenlee`
- Tailscale IP observed in prior setup: `100.89.89.70`
- Remote Hermes command: `/Users/bobeenlee/.local/bin/hermes`
- Remote CuaDriver command: `/Users/bobeenlee/.local/bin/cua-driver`
- Remote Hermes config: `/Users/bobeenlee/.hermes/config.yaml`

Do not commit `.env`; it is intentionally ignored.

## Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive. Summarize status without copying secrets.
- Prefer `bin/hermes-remote` commands over ad hoc SSH because the script captures the expected paths and backup behavior.
- Before editing remote `~/.hermes/config.yaml`, create or rely on a timestamped backup.
- Use user-level Hermes/launchd commands. Do not introduce root/system-level daemons unless a user explicitly asks.
- Do not remove remote access keys or stop the gateway unless the user asks or the rollback task requires it.
- macOS `computer_use` permissions cannot be fully automated. `grant-computer-use` opens the flow; the user may need to approve CuaDriver in System Settings.

## Core Workflow

Start every remote operations session with:

```bash
cd /Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-remote-ops
bin/hermes-remote check-ssh
bin/hermes-remote status
```

If SSH fails:

- Check Tailscale status from the Control MacBook.
- Try the configured SSH alias before changing config.
- Remember that VNC/Screen Sharing can be reachable while SSH is temporarily slow or unavailable.

## Computer Use Workflow

Use this when the remote Hermes agent needs macOS desktop control.

```bash
bin/hermes-remote setup-computer-use
bin/hermes-remote grant-computer-use
bin/hermes-remote verify-computer-use
bin/hermes-remote gateway-restart
```

Success criteria:

- `hermes computer-use status` finds `cua-driver`.
- `cua-driver permissions status` reports Accessibility and Screen Recording granted with source `driver-daemon`.
- `hermes mcp test cua-driver` discovers tools.
- `cua-driver get_screen_size` and `cua-driver list_windows` return data.

Known gotcha from prior setup: non-interactive SSH may not load `~/.local/bin`. The toolkit patches the remote Hermes wrapper PATH so Hermes can find `cua-driver`.

## Kanban Workflow

Use this when the remote Hermes agent should support durable tasks.

```bash
bin/hermes-remote setup-kanban
bin/hermes-remote status
```

Success criteria:

- `~/.hermes/kanban.db` exists on the remote Mac.
- `hermes kanban boards list` shows a current board, normally `default`.
- `hermes kanban stats` returns counts without errors.
- `kanban.dispatch_in_gateway: true` is present in config.
- Gateway logs include `kanban dispatcher: embedded in gateway`.

## Discord Thread Triage

For a Discord URL like:

```text
https://discord.com/channels/<guild_id>/<channel_id>/<message_or_thread_id>
```

Use the final ID as the thread/chat ID unless logs prove otherwise.

```bash
bin/hermes-remote is-working <thread_id>
bin/hermes-remote tail-thread <thread_id>
```

Interpretation:

- Working: recent `inbound message` without a later `response ready`, a live worker process beyond gateway/MCP, or Kanban `running > 0`.
- Done: `response ready` followed by `Sending response`, no worker process, Kanban `running 0`.
- Failed or incomplete: response exists but `errors.log` or `agent.log` shows tool/provider failures such as missing `brew`, failed deploy command, provider quota, or browser navigation errors.

## Gateway Operations

After config changes:

```bash
bin/hermes-remote gateway-restart
bin/hermes-remote status
```

Expected gateway service:

- user-level launchd
- label `ai.hermes.gateway`
- logs under `~/.hermes/logs/gateway.log` and `~/.hermes/logs/gateway.error.log`

## Dashboard Operations

The dashboard is not required for gateway operation.

```bash
bin/hermes-remote dashboard-status
bin/hermes-remote dashboard-start
```

It binds to `127.0.0.1:9119` on the remote Mac by default. Do not use insecure external binding unless explicitly requested.

## Verification Before Finishing

For script edits:

```bash
bash -n bin/hermes-remote
bin/hermes-remote check-ssh
bin/hermes-remote status
```

For docs-only edits, at least inspect changed files and run:

```bash
git diff -- hermes-remote-ops
```

## Commit Hygiene

- Keep `.env` untracked.
- Stage only intentional files under `hermes-remote-ops/` unless the user asked for broader changes.
- Existing untracked files elsewhere in the repo may belong to the user; do not remove or stage them accidentally.
