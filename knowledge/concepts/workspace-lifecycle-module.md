---
type: Concept
title: Workspace Lifecycle module
description: The repo-level interface that every Hermes task follows: choose a task type, start in the canonical workspace root, work in an isolated worktree, produce required outputs, run chec
resource: repo://hermes-workspace/knowledge/concepts/workspace-lifecycle-module.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# Workspace Lifecycle module

The repo-level interface that every Hermes task follows: choose a task type, start in the canonical workspace root, work in an isolated worktree, produce required outputs, run checks, and finish as `done` or `review-required`.
_Avoid_: ad hoc task instructions, scattered prompt rules
