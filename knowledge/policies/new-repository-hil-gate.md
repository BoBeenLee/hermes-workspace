---
type: Policy
title: New Repository HIL Gate
description: Human-in-the-loop approval policy before creating a standalone service, product, app, site, tool, or repository.
resource: repo://hermes-workspace/knowledge/policies/new-repository-hil-gate.md
tags: [hermes, hil, repository]
timestamp: 2026-06-27T00:00:00+09:00
source_path: AGENTS.md
---

# New Repository HIL Gate

When a standalone service, product, app, site, tool, or repository appears appropriate, stop before creating or cloning it and request approval.

The approval request must include owner or org, repo name, visibility, initial stack or scaffold, deployment target, and whether implementation should be delegated to Antigravity.

Repo creation, deployment setup, provider configuration, permissions, and Antigravity implementation finish as `review-required`.
