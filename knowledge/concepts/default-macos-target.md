---
type: Concept
title: Default macOS target
description: Default execution-target semantics and the concrete remote Mac profile used for Hermes workspace tasks.
resource: repo://hermes-workspace/knowledge/concepts/default-macos-target.md
tags: [hermes, concept]
timestamp: 2026-07-19T00:00:00+09:00
source_path: CONTEXT.md
---

# Default macOS target

For work in this project, an unspecified execution target means the default remote Mac, not the local control host. Operators use the local checkout as the SSH control surface and perform operational commands, task file changes, and verification in the remote workspace. A task uses the local host or another target only when the user explicitly requests it or an active target profile selects it.

The current concrete profile is defined in `config/targets/bobeen-mac.env` and `config/example.env`. It preserves the known MacBook SSH alias, user, launchd service behavior, CuaDriver paths, and workspace path so operators can act without rediscovering production details. Prefer `bin/hermes-remote` over ad hoc SSH and use the profile's `HERMES_REMOTE_WORKSPACE` as the task workspace.

_Avoid_: treating the local checkout as the default execution environment, or treating the default remote Mac as the only supported target.
