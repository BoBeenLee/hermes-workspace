---
type: Concept
title: Discord HIL Gate
description: The human-in-the-loop clarification checkpoint Hermes uses before acting on ambiguous or risky Discord requests. Hermes uses the externally installed mattpocock `grill-me` skill to
resource: repo://hermes-workspace/knowledge/concepts/discord-hil-gate.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# Discord HIL Gate

The human-in-the-loop clarification checkpoint Hermes uses before acting on ambiguous or risky Discord requests. Hermes uses the externally installed mattpocock `grill-me` skill to ask one question at a time, then waits for explicit approval before entering the Workspace Lifecycle.
_Avoid_: automatic execution from vague Discord prompts, local custom grill skill
