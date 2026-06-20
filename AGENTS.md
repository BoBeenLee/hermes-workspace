# Hermes Workspace Agent Guide

SSH-first toolkit for operating a remote Hermes Agent host. Read this before changing files here or operating a remote macOS or Linux host.

## Source Context

The operating model comes from:

- `CONTEXT.md`
- `docs/workspace-lifecycle.md`
- `docs/research-workflow.md`
- `docs/discord-thread-triage.md`
- `docs/local-llm-providers.md`
- `docs/dgx-spark-remote-access.md` for DGX Spark / AI TOP ATOM remote access
- `docs/hermes-agent.md` for the migrated first MacBook bootstrap runbook
- migrated historical plans under `docs/plans/` when they are present after repo promotion

Important terms:

- **Control host**: the local machine where Codex/Desktop automation runs.
- **Hermes host**: the remote macOS or Linux user account that runs NousResearch `hermes-agent`.
- **Default macOS target**: the current Hermes host profile in `config/targets/bobeen-mac.env`, used for the existing MacBook setup.
- **DGX Spark**: the user's NVIDIA DGX Spark / GIGABYTE AI TOP ATOM Linux workstation. It is separate from the Hermes host profile unless explicitly configured as one; use `docs/dgx-spark-remote-access.md` for SSH, dashboard, RDP/xrdp, and browser setup.
- **Hermes agent**: the per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.
- **Local LLM provider**: a Hermes model provider backed by a local or self-hosted OpenAI-compatible endpoint, such as Ollama, vLLM, SGLang, or a DGX Spark model service.
- **Remote access path**: SSH key access from the control host to a Hermes host. Tailscale/LAN aliases are access paths, not application state.
- **Workspace Lifecycle module**: the interface every Hermes task follows before it is reported as `done` or `review-required`.
- **Research Analysis module**: the interface for market research and analysis work, including brief, source ledger, notes, and report artifacts.
- **Discord HIL Gate**: the human-in-the-loop clarification checkpoint Hermes uses before acting on ambiguous or risky Discord requests.
- **Approval Summary**: the final Discord message Hermes posts after clarification, summarizing the intended work for explicit human approval.

## Target Model

Hermes operations are SSH-first and target-profile driven. Host-specific values belong in `.env` or `config/targets/<target>.env`, while the workflow should stay portable across macOS and Linux.

The original configuration names a specific MacBook because it was the first production Hermes host and needed a reliable runbook for SSH, launchd, CuaDriver, gateway logs, and the canonical workspace path. Keep those concrete values as the current default target, but write new workflow guidance in terms of a generic Hermes host unless a step is macOS-only or Linux-only.

Defaults live in `config/example.env`; local overrides live in ignored `.env`. Target examples live under `config/targets/`, with OS notes in `docs/targets/`.

## Current Default Target

The current default target is the macOS profile for the existing Hermes host:

- SSH alias: `bobeen`
- Remote user: `bobeenlee`
- observed Tailscale IP: `100.89.89.70`
- Remote Hermes command: `/Users/bobeenlee/.local/bin/hermes`
- Remote CuaDriver command: `/Users/bobeenlee/.local/bin/cua-driver`
- Remote Hermes config: `/Users/bobeenlee/.hermes/config.yaml`
- Canonical remote workspace: `/Users/bobeenlee/Workspaces/hermes-workspace`

Do not commit `.env`.

## Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive. Summarize status without copying secrets.
- Keep local model services bound to loopback by default. Prefer SSH tunnels for DGX Spark or cross-host model access; do not expose Ollama, vLLM, SGLang, or llama-server externally unless the user explicitly asks.
- Prefer `bin/hermes-remote` commands over ad hoc SSH because the script captures the expected paths and backup behavior.
- Keep migrated helper scripts under `scripts/hermes/` unless promoting them into `bin/hermes-remote` with equivalent docs and checks.
- Before editing remote `~/.hermes/config.yaml`, create or rely on a timestamped backup.
- Use user-level Hermes/launchd commands. Do not introduce root/system-level daemons unless a user explicitly asks.
- Do not remove remote access keys or stop the gateway unless the user asks or the rollback task requires it.
- macOS `computer_use` permissions cannot be fully automated. `grant-computer-use` opens the flow; the user may need to approve CuaDriver in System Settings.
- Never mark script, remote config, gateway, key/auth, or recurring automation changes as fully done without human review. Use `review-required`.
- For research-based tasks, keep a source ledger and do not present current market, product, pricing, legal, or policy claims without web verification.

## Core Workflow

Start every remote operations session with:

```bash
cd /Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Start every Hermes repo task with `docs/workspace-lifecycle.md`: choose task type, use the target profile's canonical workspace, isolate branch/worktree, produce required outputs, run checks, finish `done` or `review-required`.

If SSH fails:

- Check Tailscale status from the control host.
- Try the configured SSH alias before changing config.
- Remember that VNC/Screen Sharing can be reachable while SSH is temporarily slow or unavailable.

## Computer Use Workflow

Use `docs/workspace-lifecycle.md` plus this command path when Hermes needs macOS desktop control.

```bash
bin/hermes-remote setup-computer-use
bin/hermes-remote grant-computer-use
bin/hermes-remote verify-computer-use
bin/hermes-remote gateway-restart
```

Success: Hermes finds `cua-driver`, permissions show Accessibility + Screen Recording from `driver-daemon`, MCP test discovers tools, screen/window commands return data. Known gotcha: non-interactive SSH may miss `~/.local/bin`; toolkit patches wrapper PATH.

## Kanban Workflow

Use when Hermes needs durable tasks.

```bash
bin/hermes-remote setup-kanban
bin/hermes-remote status
```

Success: `~/.hermes/kanban.db` exists, board list shows current board, stats work, config has `kanban.dispatch_in_gateway: true`, gateway logs show `kanban dispatcher: embedded in gateway`.

## Local LLM Provider Workflow

Use `docs/local-llm-providers.md` when Hermes needs Ollama, vLLM, SGLang, DGX Spark, or another OpenAI-compatible local endpoint.

```bash
bin/hermes-remote model-status
bin/hermes-remote check-llm-endpoint http://127.0.0.1:8000/v1
```

Hermes provider changes are remote config work. Verify endpoint reachability, exact model name, API compatibility mode, context length of at least `65536` when required, and tool/reasoning parser settings for vLLM or SGLang. Finish provider setup or changes as `review-required`.

## Discord Thread Triage

Detailed workflow: `docs/discord-thread-triage.md`. Wake Hermes from the user's Discord account by mentioning `@Bob Hermes`; do not use bot/webhook activation. For Discord URLs, use the final ID as thread/chat ID unless logs prove otherwise.

```bash
bin/hermes-remote is-working <thread_id>
bin/hermes-remote tail-thread <thread_id>
```

Interpret state using `docs/discord-thread-triage.md`: recent inbound/live worker/Kanban running means working; sent response/no worker/running 0 means done; errors in logs mean failed or incomplete.

## Discord HIL Gate

When a Discord request is ambiguous or risky, Hermes must clarify before acting. Use the externally installed mattpocock `grill-me` skill, not a local custom clone, to ask one question at a time and include Hermes' recommended answer with each question.

Apply the gate when the request has unclear goals, success criteria, target workspace/repo, write scope, remote config/auth/deployment impact, recurring automation impact, Antigravity delegation, or possible standalone repo creation. Skip it for clear read-only status checks and simple thread triage.

During the gate, do not edit files, change remote config, restart the gateway, create repositories, deploy, change auth/keys, or start Antigravity. After the questions are resolved, post an Approval Summary in the same Discord thread with goal, scope/non-goals, target workspace/repo, expected changes, verification, and completion mode. Start the Workspace Lifecycle task only after explicit approval. If clarification shows a standalone repo is needed, continue into the New Repository HIL Gate.

## Market Research and Analysis

Follow `docs/research-workflow.md` for market/product/competitor/pricing/legal/policy/trend work. Current claims require web verification and a source ledger. Report-only work can be `done`; scripts, recurring automation, or remote config changes are `review-required`.

## Antigravity Delegation

Follow `docs/antigravity-delegation.md`. Hermes supervises, Antigravity implements in an isolated worktree through manual tmux or `antigravity-worker`, and completion stays `review-required`.

## New Repository HIL Gate

When a user asks for a new standalone service, product, app, site, or tool, Hermes must decide whether the request belongs in the current workspace or needs a new repository. If a new repository is appropriate, Hermes must stop before creation and request HIL approval.

The HIL request must include:

- owner or org
- repo name
- visibility: `private` or `public`
- initial stack or scaffold
- deployment target, such as `gh-pages`, Vercel, or Cloudflare Pages
- whether implementation should be delegated to Antigravity

Only after explicit approval may Hermes create the GitHub repo, clone a new remote workspace, scaffold files, delegate implementation, configure deployment, or push initial branches. Repo creation, deployment setup, provider configuration, permissions, and Antigravity implementation must finish as `review-required`.

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

It binds to `127.0.0.1:9119` on the remote host by default. Do not use insecure external binding unless explicitly requested.

## DGX Spark Operations

Use `docs/dgx-spark-remote-access.md` when the user asks about `aitopatom-36a9`, `172.30.1.87`, DGX Spark, AI TOP ATOM, DGX Dashboard, RDP, xrdp, or Chromium/Chrome on the DGX Spark.

Key reminders:

- Do not commit or print the user's SSH/RDP password.
- The DGX Spark is arm64; do not install amd64 Chrome `.deb` packages. Use Chromium arm64/snap when needed.
- The initial setup web UI on port `80` can disappear after onboarding. SSH and dashboard may still be healthy.
- The DGX Dashboard was observed at remote `127.0.0.1:11000`; use an SSH tunnel instead of external binding.
- For remote desktop, prefer the documented xrdp fallback if GNOME Remote Desktop fails with routing token or Windows App `0x207` errors.

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
- Stage only intentional files in this repository unless the user asked for broader changes.
- Existing untracked files elsewhere in the repo may belong to the user; do not remove or stage them accidentally.
