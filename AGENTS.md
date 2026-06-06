# Hermes Workspace Agent Guide

This repo is the git-backed workspace and SSH-first operations hub for the remote Hermes Agent running on the Hermes MacBook.

Use this guide before changing files in `hermes-workspace/`, creating task artifacts, or operating the remote Mac.

## Source Context

The operating model comes from:

- `CONTEXT.md`
- `docs/workspace-lifecycle.md`
- `docs/research-workflow.md`
- `docs/discord-thread-triage.md`
- migrated historical plans under `docs/plans/` when they are present after repo promotion

Important language from the plan:

- **Control MacBook**: the local Mac where Codex/Desktop automation runs.
- **Hermes MacBook**: the remote Mac that runs NousResearch `hermes-agent`.
- **Hermes agent**: the per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.
- **Remote access path**: SSH key access from Control MacBook to Hermes MacBook. Tailscale/LAN aliases are access paths, not application state.
- **Workspace Lifecycle module**: the interface every Hermes task follows before it is reported as `done` or `review-required`.
- **Research Analysis module**: the interface for market research and analysis work, including brief, source ledger, notes, and report artifacts.

## Current Default Target

Default values live in `config/example.env` and can be overridden by a local `.env`.

- SSH alias: `bobeen`
- Remote user: `bobeenlee`
- Tailscale IP observed in prior setup: `100.89.89.70`
- Remote Hermes command: `/Users/bobeenlee/.local/bin/hermes`
- Remote CuaDriver command: `/Users/bobeenlee/.local/bin/cua-driver`
- Remote Hermes config: `/Users/bobeenlee/.hermes/config.yaml`
- Canonical remote workspace: `/Users/bobeenlee/Workspaces/hermes-workspace`

Do not commit `.env`; it is intentionally ignored.

## Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive. Summarize status without copying secrets.
- Prefer `bin/hermes-remote` commands over ad hoc SSH because the script captures the expected paths and backup behavior.
- Before editing remote `~/.hermes/config.yaml`, create or rely on a timestamped backup.
- Use user-level Hermes/launchd commands. Do not introduce root/system-level daemons unless a user explicitly asks.
- Do not remove remote access keys or stop the gateway unless the user asks or the rollback task requires it.
- macOS `computer_use` permissions cannot be fully automated. `grant-computer-use` opens the flow; the user may need to approve CuaDriver in System Settings.
- Never mark script, remote config, gateway, key/auth, or recurring automation changes as fully done without human review. Use `review-required`.
- For research-based tasks, keep a source ledger and do not present current market, product, pricing, legal, or policy claims without web verification.

## Core Workflow

Start every remote operations session with:

```bash
cd /Users/mac_al03241161/Documents/mygit/hermes-workspace
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Start every Hermes repo task by applying `docs/workspace-lifecycle.md`:

- choose the task type
- use the canonical workspace root
- work in an isolated branch/worktree
- produce the required outputs
- run task-specific checks
- finish as `done` or `review-required`

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

## Market Research and Analysis

Use this when Hermes is asked for market research, competitive analysis, product analysis, pricing checks, legal/policy scans, or trend reports.

Required artifact layout:

```text
research/briefs/<YYYY-MM-DD>-<slug>.md
research/sources/<YYYY-MM-DD>-<slug>.jsonl
research/notes/<YYYY-MM-DD>-<slug>.md
reports/<YYYY-MM-DD>-<slug>.md
```

Follow `docs/research-workflow.md`. Latest information, market trends, prices, laws, policies, product comparisons, and recommendations require web verification. Report-only work can be `done`; data collection scripts, recurring automation, or remote config changes must be `review-required`.

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
rg -n "Workspace Lifecycle|Research Analysis|review-required|source ledger" .
git diff -- .
```

## Commit Hygiene

- Keep `.env` untracked.
- Stage only intentional files in this repo unless the user asked for broader changes.
- Existing untracked files elsewhere in the repo may belong to the user; do not remove or stage them accidentally.
