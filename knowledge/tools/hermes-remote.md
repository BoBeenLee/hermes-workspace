---
type: Tool
title: hermes-remote
description: SSH-first command wrapper for operating Hermes hosts using target profiles.
resource: repo://hermes-workspace/knowledge/tools/hermes-remote.md
tags: [hermes, ssh, tool]
timestamp: 2026-06-27T00:00:00+09:00
source_path: README.md
---

# hermes-remote

`bin/hermes-remote` is the preferred command wrapper for operating the remote Hermes host. It captures expected SSH aliases, target profile values, backup behavior, gateway commands, model checks, Discord thread triage commands, and research-intelligence helper commands.

## Common Checks

```bash
bin/hermes-remote check-ssh
bin/hermes-remote status
```

## Common Operations

```bash
bin/hermes-remote setup-computer-use
bin/hermes-remote verify-computer-use
bin/hermes-remote setup-kanban
bin/hermes-remote model-status
bin/hermes-remote gateway-restart
```

Prefer this wrapper over ad hoc SSH for Hermes host operations.
