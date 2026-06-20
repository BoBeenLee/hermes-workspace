# Hermes Workspace

Operator repo for managing a Hermes Agent on a remote macOS or Linux host over SSH/Tailscale.

It currently defaults to the `bobeen-mac` macOS profile, which records the first production Hermes host. That specific profile exists so operators can reliably check Hermes, install/verify `computer_use`, initialize Kanban, restart gateway, inspect Discord thread work, and keep tasks inside a git-backed workspace lifecycle without rediscovering host paths.

The general model is target-profile based: macOS hosts may use launchd and CuaDriver desktop control, while Linux hosts use the same SSH and workspace lifecycle without macOS desktop control until a Linux backend is configured. Local or self-hosted model providers are handled through OpenAI-compatible endpoints; see [docs/local-llm-providers.md](docs/local-llm-providers.md).

It also records the DGX Spark / AI TOP ATOM remote access path for `bobeenlee`, including SSH, DGX Dashboard tunneling, RDP/xrdp setup, and Chromium-on-arm64 notes. See [docs/dgx-spark-remote-access.md](docs/dgx-spark-remote-access.md).

Discord requests that are ambiguous or risky pass through a human-in-the-loop clarification gate before execution. Hermes uses the external mattpocock `grill-me` skill for one-question-at-a-time clarification, then waits for an Approval Summary to be approved in the Discord thread.

Historical Hermes bootstrap material migrated from `bbl-ai-lab` lives in [docs/hermes-agent.md](docs/hermes-agent.md), [docs/plans/36-macbook-remote-hermes-agent.md](docs/plans/36-macbook-remote-hermes-agent.md), and [scripts/hermes/](scripts/hermes/). Prefer `bin/hermes-remote` for current operations, and keep the migrated scripts as legacy helpers or migration sources unless they are deliberately promoted into the main CLI.

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

For another target, use that profile's `HERMES_REMOTE_WORKSPACE` instead, such as `/home/<user>/Workspaces/hermes-workspace` on Linux.

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
bin/hermes-remote model-status
bin/hermes-remote check-llm-endpoint http://127.0.0.1:8000/v1
bin/hermes-remote antigravity-check
bin/hermes-remote gateway-restart
bin/hermes-remote is-working 1512384300689916064
bin/hermes-remote tail-thread 1512384300689916064
bin/hermes-remote run "Use computer_use to report two visible apps."
```

See `bin/hermes-remote help` for full CLI surface. Antigravity setup, auth, run, MCP worker, and collect commands are documented in [docs/antigravity-delegation.md](docs/antigravity-delegation.md).

Legacy bootstrap and browser-provider helpers are available under `scripts/hermes/`:

```bash
scripts/hermes/doctor.sh
scripts/hermes/install.sh --dry-run
scripts/hermes/camofox_ask_three.py --prompt "Reply briefly."
```

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

Discord HIL clarification is documented in [docs/discord-thread-triage.md](docs/discord-thread-triage.md), with repo-local Discord tool usage captured in [skills/discord.SKILL.md](skills/discord.SKILL.md). The remote Hermes profile should have `grill-me` installed from `mattpocock/skills`:

```bash
npx -y skills@latest add https://github.com/mattpocock/skills --skill grill-me --yes --global
```

Market research and analysis tasks use the Research Analysis module in [docs/research-workflow.md](docs/research-workflow.md). Research-based work writes briefs, source ledgers, notes, and reports under:

```text
research/
reports/
```

Local LLM provider operations use [docs/local-llm-providers.md](docs/local-llm-providers.md). Use it when connecting Hermes to Ollama, vLLM, SGLang, or a DGX Spark model server. Provider config changes are remote config work and should finish as `review-required`.

## Notes

- The repo does not store SSH keys, provider keys, Discord tokens, or Hermes secrets.
- Remote config changes are backed up under `~/.hermes/config.yaml.bak-remote-ops-*`.
- The script reads target values from `.env` or `config/example.env`; copy from `config/targets/bobeen-mac.env` or `config/targets/linux-example.env` when setting up another host.
