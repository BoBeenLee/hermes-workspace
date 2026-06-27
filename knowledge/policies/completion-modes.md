---
type: Policy
title: Completion Modes
description: Rules for deciding whether Hermes work finishes as done or review-required.
resource: repo://hermes-workspace/knowledge/policies/completion-modes.md
tags: [hermes, completion, review-required]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/workspace-lifecycle.md
---

# Completion Modes

Use `done` only when required artifacts or checks are complete and no human review is needed before merge, operational application, production-like changes, or spending.

Use `review-required` for code or shell script changes, data collection scripts, recurring automation, remote config changes, repository creation, deployment setup, gateway restarts, launchd changes, permission grants, key/auth changes, Antigravity delegated implementation, and any task where human approval is required before application.

Every task completion note records task type, HIL status, branch/worktree or none, changed files or report path, tests/checks run, source ledger path when research-based, and completion mode.
