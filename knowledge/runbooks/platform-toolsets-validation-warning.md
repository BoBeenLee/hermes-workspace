---
type: Runbook
title: Platform Toolsets Validation Warning
description: Why `hermes config migrate` reports MCP server toolsets as unknown, and why the config must not be edited to silence it.
resource: repo://hermes-workspace/knowledge/runbooks/platform-toolsets-validation-warning.md
tags: [hermes, mcp, toolsets, config, false-positive]
timestamp: 2026-08-17T13:00:00+09:00
---

# Platform Toolsets Validation Warning

## Symptom

`hermes config migrate` prints warnings naming the remote Mac's MCP servers:

```text
⚠ platform 'cli' references unknown toolset 'antigravity-worker' — did you mean 'hermes-cli'?
⚠ platform 'cli' references unknown toolset 'openhuman-kakaotalk-mac' — did you mean 'hermes-cli'?
⚠ platform 'discord' references unknown toolset 'antigravity-worker' — did you mean 'hermes-discord'?
```

First observed on the default remote Mac during the Hermes 0.19.1 → 0.20.2 upgrade (2026-08-17), when the config schema moved v33 → v37.

## Verdict

**False positive. Do not edit `platform_toolsets` and do not apply the suggested `hermes-cli` / `hermes-discord` rename.**

The config is correct. The validator is MCP-unaware in the process where it runs.

## Root cause

- An MCP server registers its own name as a toolset alias only when it connects and successfully registers tools: `registry.register_toolset_alias(name, toolset_name)` in `tools/mcp_tool.py` (two call sites, ~`:6523` and `:6696`).
- `validate_toolset()` in `toolsets.py` accepts static `TOOLSETS`, plugin toolset names, and **live registry aliases**.
- `hermes config migrate` runs the check via `validate_platform_toolsets()` (`hermes_cli/config.py`, `hermes_cli/toolset_validation.py`) in a short-lived CLI process that never connects MCP servers. The aliases do not exist yet, so every MCP-server toolset name looks unknown.

The validator itself exists for a real bug (upstream #38798, where a migration rewrote `hermes-cli` to `hermes` and silently emptied the tool list). It is worth keeping; it just cannot see MCP aliases at migrate time.

## Why editing the config would break things

`platform_toolsets` is a whitelist, not a hint. An empty list yields zero tools for that platform — see the `platform_toolsets: telegram: []` comments in `agent/agent_init.py` and `tools/mcp_tool.py`. Removing `antigravity-worker` from `platform_toolsets.cli` silences the warning **and disables those MCP tools for the CLI platform**.

## Verification performed

| Check | Result |
|---|---|
| `hermes -t zzz-not-a-real-toolset -z ...` | Rejected: `ignoring unknown --toolsets entries` + `did not contain any valid toolsets` |
| `hermes -t antigravity-worker -z ...` | No rejection; exposes `mcp__antigravity_worker__antigravity_{start_task,check,status,collect,stop}` |
| `hermes -t openhuman-kakaotalk-mac -z ...` | No rejection; runs normally |
| `hermes doctor` | Zero toolset warnings |
| Gateway logs (default + content/jarvis/preflight/product) | Zero `unknown toolset` / `zero valid toolsets` entries |

The bogus-name case is the control: a genuinely invalid toolset is loud and distinguishable.

## How to re-check

```bash
ssh bobeen 'PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$PATH"; hermes -t antigravity-worker -z "say OK"'
ssh bobeen 'PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$PATH"; hermes doctor 2>&1 | grep -i toolset'
```

If the first command prints `ignoring unknown --toolsets entries`, the toolset really is broken and the warning is no longer a false positive. Silence from both commands means the config is healthy.

## Scope

The warning only appears while `hermes config migrate` runs, which happens on a config schema bump. It is not emitted by `hermes doctor`, the gateway, or normal agent runs. Treat it as noise until upstream teaches the validator about MCP aliases.
