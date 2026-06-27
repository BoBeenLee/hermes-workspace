# Hermes Workspace

Operator repo for managing remote Hermes Agent hosts over SSH/Tailscale.

The canonical durable knowledge base is now the OKF bundle at [knowledge/index.md](knowledge/index.md). Root files are intentionally thin entrypoints; new durable documentation should be written under `knowledge/` according to [Knowledge Authoring Rules](knowledge/policies/authoring-rules.md).

## Quick Start

Agent and Claude-style operators should read [AGENTS.md](AGENTS.md) first.

```bash
cp config/example.env .env
bin/hermes-remote check-ssh
bin/hermes-remote status
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
bin/hermes-remote gateway-restart
bin/hermes-remote is-working <discord_thread_id>
bin/hermes-remote tail-thread <discord_thread_id>
```

See [knowledge/tools/hermes-remote.md](knowledge/tools/hermes-remote.md) and `bin/hermes-remote help` for the command surface.

## Knowledge Map

- [Concepts](knowledge/concepts/index.md)
- [Workflows](knowledge/workflows/index.md)
- [Runbooks](knowledge/runbooks/index.md)
- [Tools](knowledge/tools/index.md)
- [Skills](knowledge/skills/index.md)
- [Policies](knowledge/policies/index.md)
- [Plans](knowledge/plans/index.md)

Task artifacts remain in `tasks/`, `research/`, `reports/`, and `artifacts/`.
