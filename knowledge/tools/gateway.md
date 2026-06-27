---
type: Tool
title: Hermes Gateway
description: User-level Hermes gateway service and log inspection entry point.
resource: repo://hermes-workspace/knowledge/tools/gateway.md
tags: [hermes, gateway, launchd]
timestamp: 2026-06-27T00:00:00+09:00
source_path: AGENTS.md
---

# Hermes Gateway

The expected gateway service is the user-level launchd label `ai.hermes.gateway`. Logs live under `~/.hermes/logs/gateway.log` and `~/.hermes/logs/gateway.error.log` on the active Hermes host.

After remote config changes, restart and verify through the wrapper:

```bash
bin/hermes-remote gateway-restart
bin/hermes-remote status
```

Gateway restarts, launchd changes, auth changes, and remote config changes finish as `review-required`.
