---
type: Runbook
title: Linux Target Profile
description: Target profile notes for Linux Hermes hosts.
resource: repo://hermes-workspace/knowledge/runbooks/linux-target-profile.md
tags: [hermes, linux, target]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/targets/linux.md
---

# Linux Target Profile

Use a Linux target profile when a remote Hermes agent should share the same git-backed workspace lifecycle without macOS desktop control.

Start from:

```bash
cp config/targets/linux-example.env config/targets/<target>.env
```

Then replace the placeholder host, user, and paths:

```env
HERMES_REMOTE_OS=linux
HERMES_SERVICE_MANAGER=systemd
HERMES_COMPUTER_USE_BACKEND=none
HERMES_REMOTE_HOME=/home/<user>
HERMES_BIN=/home/<user>/.local/bin/hermes
HERMES_CONFIG=/home/<user>/.hermes/config.yaml
HERMES_REMOTE_WORKSPACE=/home/<user>/Workspaces/hermes-workspace
```

Optional local LLM provider hints:

```env
HERMES_LLM_PROVIDER=custom:llama-local
HERMES_LLM_BASE_URL=http://127.0.0.1:8080/v1
HERMES_LLM_MODEL=<served-model-name>
HERMES_LLM_CONTEXT_LENGTH=65536
```

These are hints only: `model-status` uses them to probe reachability and to redact
the URL. They do not configure Hermes. `65536` is a hard floor, not a preference -
Hermes rejects a primary model under 64K context.

Supported operations:

- SSH connectivity and status checks.
- Gateway status/restart through the Hermes CLI when the installed Hermes CLI supports the host service manager.
- Kanban setup and diagnostics.
- Dashboard start/status.
- Discord thread triage from Hermes logs.
- One-shot Hermes prompts without `computer_use`.

Unsupported until a Linux desktop-control backend is added:

- `setup-computer-use`
- `grant-computer-use`
- `verify-computer-use`

Those commands should exit with a clear unsupported target/backend message when `HERMES_COMPUTER_USE_BACKEND=none`.

Adding a Linux desktop-control backend would still not bring KakaoTalk with it. See
[KakaoTalk Control Portability](kakaotalk-control-portability.md) for what the macOS
stack actually depends on and why the account device slot decides the question.

## Verified On The DGX Spark (2026-09-13)

Everything in the "Supported operations" list above is now measured, not assumed, on
`config/targets/dgx-spark.env` (Ubuntu 24.04.4 aarch64, Hermes Agent v0.21.2):

| Command | Result |
| --- | --- |
| `check-ssh` | ok |
| `status` | `target_os=linux service_manager=systemd computer_use_backend=none` |
| `model-status` / `check-llm-endpoint http://127.0.0.1:8080/v1` | ok, llama.cpp `/v1/models` answers |
| `run "Reply with exactly: OK"` | `OK` |
| `setup-kanban` | board created |
| `setup-computer-use` / `grant-computer-use` / `verify-computer-use` | **exit 2**, `computer_use is unsupported for this target.` |

The gateway runs as the systemd **user** unit `hermes-gateway.service` with lingering
enabled, installed by `hermes gateway install` with no sudo. `doctor.sh` now reports
`systemd_gateway_active`, `systemd_gateway_enabled`, and `systemd_linger`.

Still unverified: long-run gateway stability, behaviour across a host reboot, and
whether the local model survives memory pressure from a concurrent ComfyUI job.

Linux notes:

- `HERMES_REMOTE_HOST` must include the remote user (`user@host`) unless an
  `~/.ssh/config` alias supplies it. `bin/hermes-remote` sshs to that value verbatim;
  only `install.sh` / `doctor.sh` prepend `HERMES_REMOTE_USER`.
- Keep the example profile non-runnable until a real SSH host is known.
- Do not add root/system daemon commands to this repo. Prefer the Hermes CLI gateway commands and document any host-specific service setup separately.
- The workspace repo remains `git@github.com:BoBeenLee/hermes-workspace.git` unless the target intentionally uses a fork.
