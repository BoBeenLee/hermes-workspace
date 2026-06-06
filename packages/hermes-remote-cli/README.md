# hermes-remote-cli

Shared CLI package for operating remote Hermes Agent installations.

Invoke through the workspace wrapper:

```bash
../../bin/hermes-remote --project bobeen status
```

The CLI loads configuration in this order:

1. `hermes-remote-ops/.env` for local defaults, if present
2. `--config PATH`, if supplied
3. `projects/<name>.env`, when `--project <name>` or `HERMES_REMOTE_PROJECT` is set
4. `projects/default.env`, if present
5. `config/example.env` fallback
