---
type: Concept
title: New repository HIL gate
description: The approval checkpoint Hermes must use before creating a new GitHub repository, cloning a new service workspace, or changing deployment/provider configuration for a standalone pro
resource: repo://hermes-workspace/knowledge/concepts/new-repository-hil-gate.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# New repository HIL gate

The approval checkpoint Hermes must use before creating a new GitHub repository, cloning a new service workspace, or changing deployment/provider configuration for a standalone product or service. Hermes may infer that a new repository is appropriate, but must ask the human to approve owner, repo name, visibility, stack, deployment target, and delegation mode before taking creation or setup actions.
_Avoid_: automatic repo creation, implicit product workspace setup
