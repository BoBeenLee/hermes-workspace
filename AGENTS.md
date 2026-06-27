# Hermes Workspace Agent Guide

This repository is an SSH-first operator workspace for remote Hermes Agent hosts. The canonical durable knowledge base is the OKF bundle at [knowledge/index.md](knowledge/index.md).

## Start Here

Start every Hermes repo or remote-operations session from this workspace:

```bash
cd /Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Use [knowledge/workflows/workspace-lifecycle.md](knowledge/workflows/workspace-lifecycle.md) for task lifecycle rules. Use [knowledge/policies/authoring-rules.md](knowledge/policies/authoring-rules.md) for new durable documentation.

## Default Target

- SSH alias: `bobeen`
- Remote user: `bobeenlee`
- Remote Hermes command: `/Users/bobeenlee/.local/bin/hermes`
- Remote CuaDriver command: `/Users/bobeenlee/.local/bin/cua-driver`
- Remote Hermes config: `/Users/bobeenlee/.hermes/config.yaml`
- Canonical remote workspace: `/Users/bobeenlee/Workspaces/hermes-workspace`

Target details live in `config/example.env` and `config/targets/`. Do not commit `.env`.

## Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive.
- Prefer `bin/hermes-remote` over ad hoc SSH.
- Keep local model services bound to loopback by default; prefer SSH tunnels for cross-host access.
- Before remote `~/.hermes/config.yaml` edits, create or rely on a timestamped backup.
- Do not remove remote access keys, stop the gateway, change auth, or alter recurring automation unless explicitly asked.
- Script, remote config, gateway, key/auth, permission, deployment, and recurring automation changes finish as `review-required`.
- Research-based tasks need web verification and a source ledger.

See [knowledge/policies/safety-rules.md](knowledge/policies/safety-rules.md) and [knowledge/policies/completion-modes.md](knowledge/policies/completion-modes.md).

## Core Workflows

- Workspace lifecycle: [knowledge/workflows/workspace-lifecycle.md](knowledge/workflows/workspace-lifecycle.md)
- Research analysis: [knowledge/workflows/research-analysis.md](knowledge/workflows/research-analysis.md)
- Discord triage: [knowledge/workflows/discord-thread-triage.md](knowledge/workflows/discord-thread-triage.md)
- Antigravity delegation: [knowledge/workflows/antigravity-delegation.md](knowledge/workflows/antigravity-delegation.md)
- New repository HIL gate: [knowledge/policies/new-repository-hil-gate.md](knowledge/policies/new-repository-hil-gate.md)

## Important Runbooks

- DGX Spark: [knowledge/runbooks/dgx-spark-remote-access.md](knowledge/runbooks/dgx-spark-remote-access.md)
- Hermes bootstrap: [knowledge/runbooks/hermes-agent-bootstrap.md](knowledge/runbooks/hermes-agent-bootstrap.md)
- Multi-host bootstrap: [knowledge/runbooks/hermes-agent-multi-host.md](knowledge/runbooks/hermes-agent-multi-host.md)
- Local LLM providers: [knowledge/tools/local-llm-providers.md](knowledge/tools/local-llm-providers.md)

## Verification

For docs-only changes:

```bash
python3 scripts/hermes/validate_okf.py
git diff -- .
```

For ops script changes:

```bash
bash -n bin/hermes-remote
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Keep `.env` untracked. Stage only intentional files.
