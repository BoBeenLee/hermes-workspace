# macOS Target Profile

Use a macOS target profile when the remote Hermes agent runs on a user-level macOS account and may need CuaDriver desktop control.

The current default profile is:

```bash
bin/hermes-remote --target bobeen-mac config
```

Required profile fields:

```env
HERMES_REMOTE_OS=macos
HERMES_SERVICE_MANAGER=launchd
HERMES_COMPUTER_USE_BACKEND=cua-driver
HERMES_REMOTE_HOME=/Users/<user>
HERMES_BIN=/Users/<user>/.local/bin/hermes
HERMES_CONFIG=/Users/<user>/.hermes/config.yaml
HERMES_WORKSPACE_ROOT=/Users/<user>/Workspaces/hermes-workspace
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
