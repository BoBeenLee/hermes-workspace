---
type: Policy
title: Knowledge Authoring Rules
description: Rules for writing future durable Hermes knowledge documents in the OKF bundle.
resource: repo://hermes-workspace/knowledge/policies/authoring-rules.md
tags: [hermes, okf, authoring]
timestamp: 2026-06-27T00:00:00+09:00
---

# Knowledge Authoring Rules

New durable knowledge documents must be created under `knowledge/` unless they are task artifacts, generated transcripts, reports, or temporary notes.

Every non-index knowledge document must include OKF frontmatter with `type`, `title`, `description`, `resource`, `tags`, and `timestamp`. Use `source_path` when the document was migrated or derived from another repo path.

Subdirectory `index.md` files are table-of-contents files and do not use frontmatter. New knowledge documents must be linked from the nearest `index.md`; broadly important documents should also be linked from `knowledge/index.md`.

Task artifacts remain under `tasks/`, `research/`, `reports/`, or `artifacts/` according to the Workspace Lifecycle and Research Analysis workflows.

Root `README.md`, `AGENTS.md`, and `CLAUDE.md` stay thin and point into `knowledge/`.
