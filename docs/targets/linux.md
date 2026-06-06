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
HERMES_WORKSPACE_ROOT=/home/<user>/Workspaces/hermes-workspace
```

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

Linux notes:

- Keep the example profile non-runnable until a real SSH host is known.
- Do not add root/system daemon commands to this repo. Prefer the Hermes CLI gateway commands and document any host-specific service setup separately.
- The workspace repo remains `git@github.com:BoBeenLee/hermes-workspace.git` unless the target intentionally uses a fork.
