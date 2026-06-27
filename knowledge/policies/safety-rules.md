---
type: Policy
title: Safety Rules
description: Secret handling, remote configuration, model endpoint, and operational safety rules for Hermes work.
resource: repo://hermes-workspace/knowledge/policies/safety-rules.md
tags: [hermes, safety, secrets]
timestamp: 2026-06-27T00:00:00+09:00
source_path: AGENTS.md
---

# Safety Rules

- Never commit SSH private keys, provider API keys, OAuth tokens, Discord tokens, `.env` files, or remote Hermes secrets.
- Treat `~/.hermes/.env`, `~/.hermes/auth.json`, and provider config output as sensitive. Summarize status without copying secrets.
- Keep local model services bound to loopback by default. Prefer SSH tunnels for cross-host model access.
- Prefer `bin/hermes-remote` over ad hoc SSH.
- Before editing remote `~/.hermes/config.yaml`, create or rely on a timestamped backup.
- Use user-level Hermes and launchd commands. Do not introduce root/system-level daemons unless explicitly asked.
- Never mark script, remote config, gateway, key/auth, or recurring automation changes as fully done without human review. Use `review-required`.
- For research-based tasks, keep a source ledger and do not present current claims without web verification.
