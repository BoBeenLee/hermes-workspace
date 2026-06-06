# Hermes Workspace Agent Guide

This repo has two roles:

- **Control-side remote ops**: SSH-first tooling used from the Control MacBook to operate a configured Hermes target.
- **Hermes-side workspace**: the git-backed workspace used by the remote Hermes agent for task artifacts, reports, research, and repo-local work.

Use this guide before changing files in `hermes-workspace/`, creating task artifacts, or operating a remote target. First decide which role you are acting in.

## Source Context

The operating model comes from:

- `CONTEXT.md`
- `docs/workspace-lifecycle.md`
- `docs/research-workflow.md`
- `docs/discord-thread-triage.md`
- migrated historical plans under `docs/plans/` when they are present after repo promotion

Important language from the plan:

- **Control MacBook**: the local Mac where Codex/Desktop automation runs.
- **Hermes target**: a configured remote host that runs NousResearch `hermes-agent`.
- **Hermes MacBook**: the current default macOS Hermes target.
- **Hermes agent**: the per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.
- **Remote access path**: SSH key access from Control MacBook to a Hermes target. Tailscale/LAN aliases are access paths, not application state.
- **Target profile**: `config/targets/<name>.env`, the selected host/OS/path/backend contract for `bin/hermes-remote`.
- **Remote workspace manager**: the profile-aware `bin/hermes-remote` interface for checking SSH, status, gateway, Kanban, dashboard, logs, Discord thread work, and OS-specific capabilities.
- **Computer-use backend**: the profile field that determines desktop-control support. `cua-driver` is macOS-only; `none` means computer-use commands are unsupported for that target.
- **Workspace Lifecycle module**: the interface every Hermes task follows before it is reported as `done` or `review-required`.
- **Research Analysis module**: the interface for market research and analysis work, including brief, source ledger, notes, and report artifacts.

## Target Profiles

Target defaults live in `config/targets/<target>.env` and can be overridden by a local `.env`.

- Default target: `bobeen-mac`
- Default SSH alias: `bobeen`
- Default remote user: `bobeenlee`
- Default Tailscale IP observed in prior setup: `100.89.89.70`
- Default remote Hermes command: `/Users/bobeenlee/.local/bin/hermes`
- Default remote CuaDriver command: `/Users/bobeenlee/.local/bin/cua-driver`
- Default remote Hermes config: `/Users/bobeenlee/.hermes/config.yaml`
- Default canonical remote workspace: `/Users/bobeenlee/Workspaces/hermes-workspace`

Do not commit `.env`; it is intentionally ignored.

## Shared Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive. Summarize status without copying secrets.
- Never mark script, remote config, gateway, key/auth, or recurring automation changes as fully done without human review. Use `review-required`.
- For research-based tasks, keep a source ledger and do not present current market, product, pricing, legal, or policy claims without web verification.

## Control-Side Remote Ops

Use this role when operating from the Control MacBook. Start every remote operations session with:

```bash
cd /Users/mac_al03241161/Documents/mygit/hermes-workspace
bin/hermes-remote --target bobeen-mac config
bin/hermes-remote --target bobeen-mac check-ssh
bin/hermes-remote --target bobeen-mac status
```

Remote ops rules:

- Prefer `bin/hermes-remote` commands over ad hoc SSH because the script captures expected paths and backup behavior.
- Select targets with `--target <name>` or `HERMES_TARGET=<name>`; do not add host-specific paths directly to `bin/hermes-remote`.
- Before editing remote `~/.hermes/config.yaml`, create or rely on a timestamped backup.
- Use user-level Hermes/launchd commands. Do not introduce root/system-level daemons unless a user explicitly asks.
- Do not remove remote access keys or stop the gateway unless the user asks or the rollback task requires it.
- macOS `computer_use` permissions cannot be fully automated. `grant-computer-use` opens the flow for `cua-driver` targets; the user may need to approve CuaDriver in System Settings.
- Linux targets should keep `HERMES_COMPUTER_USE_BACKEND=none` until a supported Linux desktop-control backend is added.

If SSH fails:

- Check Tailscale status from the Control MacBook.
- Try the configured SSH alias before changing config.
- Remember that VNC/Screen Sharing can be reachable while SSH is temporarily slow or unavailable.

## Hermes-Side Workspace Work

Use this role when the remote Hermes agent is handling a task from Discord, CLI, Kanban, or another gateway surface. Start every Hermes repo task by applying `docs/workspace-lifecycle.md`:

- choose the task type
- use the canonical workspace root
- work in an isolated branch/worktree
- produce the required outputs
- run task-specific checks
- finish as `done` or `review-required`

Workspace rules:

- Do not treat general chat, standalone news questions, or casual Q&A as repo work unless the user asks for a repo artifact or operation.
- Before using `session_search`, decide whether the user is continuing prior work or asking a standalone question. Discard search results that conflict with the current user intent.
- Stop after two repeated failures from the same external CLI/API path and report the blocker instead of trying command variants until the turn budget is exhausted.
- Report-only research can finish as `done`; code, scripts, remote config, recurring automation, gateway operations, and key/auth changes finish as `review-required`.

## Computer Use Workflow

Use this from the Control-side remote ops role when a macOS/cua-driver target needs desktop control.

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

Known gotcha from prior setup: non-interactive SSH may not load `~/.local/bin`. The toolkit patches the remote Hermes wrapper PATH so Hermes can find `cua-driver`. These commands intentionally fail on Linux or `none` backend targets.

## Kanban Workflow

Use this from the Control-side remote ops role when the remote Hermes agent should support durable tasks.

```bash
bin/hermes-remote setup-kanban
bin/hermes-remote status
```

Success criteria:

- `~/.hermes/kanban.db` exists on the remote target.
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

Use this from the Hermes-side workspace role when Hermes is asked for market research, competitive analysis, product analysis, pricing checks, legal/policy scans, or trend reports.

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

Expected gateway service for the default macOS target:

- user-level launchd
- label `ai.hermes.gateway`
- logs under `~/.hermes/logs/gateway.log` and `~/.hermes/logs/gateway.error.log`

## Dashboard Operations

The dashboard is not required for gateway operation.

```bash
bin/hermes-remote dashboard-status
bin/hermes-remote dashboard-start
```

It binds to `127.0.0.1:9119` on the remote target by default. Do not use insecure external binding unless explicitly requested.

## Verification Before Finishing

For script edits:

```bash
bash -n bin/hermes-remote
bin/hermes-remote --target bobeen-mac check-ssh
bin/hermes-remote --target bobeen-mac status
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
