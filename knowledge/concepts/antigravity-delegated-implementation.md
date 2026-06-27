---
type: Concept
title: Antigravity delegated implementation
description: A supervised implementation flow where Hermes creates an isolated remote git worktree, starts Antigravity CLI as an implementation worker through the `antigravity-worker` MCP tools
resource: repo://hermes-workspace/knowledge/concepts/antigravity-delegated-implementation.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# Antigravity delegated implementation

A supervised implementation flow where Hermes creates an isolated remote git worktree, starts Antigravity CLI as an implementation worker through the `antigravity-worker` MCP toolset or manual tmux path, and then verifies the resulting diff, checks, logs, and completion note before any merge or operational application.
_Avoid_: unattended Antigravity automation, gateway-owned Antigravity task
