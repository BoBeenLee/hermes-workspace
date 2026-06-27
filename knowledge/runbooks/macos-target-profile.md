---
type: Runbook
title: macOS Target Profile
description: Target profile notes for macOS Hermes hosts.
resource: repo://hermes-workspace/knowledge/runbooks/macos-target-profile.md
tags: [hermes, macos, target]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/targets/macos.md
---

# macOS Target Profile

Use a macOS target profile when the remote Hermes agent runs on a user-level macOS account and may need CuaDriver desktop control.

The current default profile is:

```bash
cp config/targets/bobeen-mac.env .env
bin/hermes-remote status
```

Required profile fields:

```env
HERMES_REMOTE_OS=macos
HERMES_SERVICE_MANAGER=launchd
HERMES_COMPUTER_USE_BACKEND=cua-driver
HERMES_REMOTE_HOME=/Users/<user>
HERMES_BIN=/Users/<user>/.local/bin/hermes
HERMES_CONFIG=/Users/<user>/.hermes/config.yaml
HERMES_REMOTE_WORKSPACE=/Users/<user>/Workspaces/hermes-workspace
```

Optional local LLM provider hints:

```env
HERMES_LLM_PROVIDER=ollama
HERMES_LLM_BASE_URL=http://127.0.0.1:11434/v1
HERMES_LLM_MODEL=<model-name>
HERMES_LLM_CONTEXT_LENGTH=65536
```

Supported operations:

- SSH connectivity and status checks.
- Gateway restart through the Hermes CLI.
- Kanban setup and diagnostics.
- Dashboard start/status.
- Discord thread triage from Hermes logs.
- CuaDriver setup, permission grant flow, and verification.

macOS notes:

- `grant-computer-use` can open the permission flow, but the user may still need to approve Accessibility and Screen Recording in System Settings.
- `setup-computer-use` may patch the Hermes wrapper PATH so non-interactive SSH can find `cua-driver`.
- Keep host-specific paths in `config/targets/<target>.env`, not in `bin/hermes-remote`.
