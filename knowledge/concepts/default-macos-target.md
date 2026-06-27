---
type: Concept
title: Default macOS target
description: The current concrete Hermes host profile in `config/targets/bobeen-mac.env` and `config/example.env`. It preserves the known MacBook SSH alias, user, launchd service behavior, CuaD
resource: repo://hermes-workspace/knowledge/concepts/default-macos-target.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# Default macOS target

The current concrete Hermes host profile in `config/targets/bobeen-mac.env` and `config/example.env`. It preserves the known MacBook SSH alias, user, launchd service behavior, CuaDriver paths, and workspace path so operators can act without rediscovering production details.
_Avoid_: treating the default target as the only supported operating model
