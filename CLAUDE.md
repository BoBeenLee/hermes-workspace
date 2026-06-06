# Claude Guide

Follow `AGENTS.md` in this directory. First decide whether you are doing Control-side remote ops or Hermes-side workspace work.

Control-side remote ops quick start. Select a target profile explicitly unless the default `bobeen-mac` target is intended:

```bash
cd /Users/mac_al03241161/Documents/mygit/hermes-workspace
bin/hermes-remote --target bobeen-mac config
bin/hermes-remote --target bobeen-mac check-ssh
bin/hermes-remote --target bobeen-mac status
```

For Hermes-side workspace work, follow `docs/workspace-lifecycle.md`. For market research or analysis, follow `docs/research-workflow.md` and keep a source ledger.

Do not commit `.env`, SSH keys, API keys, OAuth tokens, Discord tokens, or copied remote Hermes secret files.
