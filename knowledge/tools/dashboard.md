---
type: Tool
title: Hermes Dashboard
description: Optional dashboard service for Hermes host inspection.
resource: repo://hermes-workspace/knowledge/tools/dashboard.md
tags: [hermes, dashboard, tool]
timestamp: 2026-06-27T00:00:00+09:00
source_path: AGENTS.md
---

# Hermes Dashboard

The dashboard is optional and not required for gateway operation. It binds to `127.0.0.1:9119` on the remote host by default.

```bash
bin/hermes-remote dashboard-status
bin/hermes-remote dashboard-start
```

Do not use insecure external binding unless explicitly requested.
