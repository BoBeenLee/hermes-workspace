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

Desktop control (`computer_use`) works on Linux. It was never the platform that
blocked it - see [Computer Use On A Linux Target](#computer-use-on-a-linux-target)
below. The commands exit 2 only when `HERMES_COMPUTER_USE_BACKEND` is not
`cua-driver`; `noop` is the value that switches the tool off.

## Computer Use On A Linux Target

`cua-driver` is cross-platform Rust, not a macOS bundle, and the upstream Hermes
installer already places a `linux-arm64` build in `~/.local/bin`. On Linux it
drives AT-SPI for the accessibility tree and XTest for input, so what it needs is
a reachable display with AT-SPI running - nothing to port.

```env
HERMES_COMPUTER_USE_BACKEND=cua-driver
CUA_BIN=<home>/.local/bin/cua-driver
HERMES_REMOTE_DISPLAY=:10
HERMES_REMOTE_XAUTHORITY=<home>/.Xauthority
```

Four things cost time on the DGX, and none of them are the driver.

**`none` is not an upstream value.** `tools/computer_use/tool.py` accepts `cua`,
`cua-driver`, `""` or `noop` and raises `RuntimeError` on anything else. The
earlier profiles said `none`, which only stayed harmless because `run_prompt`
bypasses the env-injecting code path.

**`hermes doctor` showing `✓ computer_use` proves almost nothing.**
`check_computer_use_requirements()` tests that the OS is Linux and that a file
named `cua-driver` is on the PATH. It does not look at `DISPLAY`, AT-SPI, or
whether the driver can start.

**A non-interactive SSH has no `DISPLAY`.** It has to be named in the profile and
injected - not only into `remote_bash`, but into the direct `ssh_remote` calls
and `run_prompt`, because the agent spawns `cua-driver` itself and the display
has to reach the agent rather than the ssh wrapper.

**An empty desktop looks exactly like a broken one.** `list_windows` returning
`{"windows": []}` on a healthy X11 display usually means no application is open;
GNOME's own service windows do not count as top-level. Launch something
(`cua-driver call launch_app`) before concluding anything. A locked session
produces the same empty list, so check both: `dbus-send ... org.gnome.ScreenSaver.GetActive`
and `loginctl show-session <id> -p LockedHint`.

On this host the desktop is the persistent GNOME X11 session xrdp keeps alive
(`sesman.ini`: `KillDisconnected=false`, `DisconnectedTimeLimit=0`). `gdm` is
stopped and seat0 holds no session, so `:10` is the only desktop and it survives
disconnects. No Xvfb, no autologin. For unattended use the screen lock has to be
off (`org.gnome.desktop.screensaver lock-enabled false`, `session idle-delay 0`)
- weigh that against who can reach the RDP port first.

Upstream labels Linux support alpha. Measured working: `list_windows`,
`get_screen_size`, `check_permissions` (`atspi`/`x11`/`xsend_event` all true),
`launch_app`, and an agent answering from `bin/hermes-remote run`.

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
