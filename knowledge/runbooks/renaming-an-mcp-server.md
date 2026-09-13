---
type: Runbook
title: Renaming An MCP Server
description: Every place a Hermes MCP server name is duplicated, learned the hard way while renaming openhuman-kakaotalk-mac. The top-level config.yaml is roughly a quarter of it.
resource: repo://hermes-workspace/knowledge/runbooks/renaming-an-mcp-server.md
tags: [hermes, mcp, config, rename, operations]
timestamp: 2026-09-13T22:50:00+09:00
---

# Renaming An MCP Server

Renaming `openhuman-kakaotalk-mac` to `openhuman-kakaotalk` on 2026-09-13 looked like a
two-line config edit. It was seven places, and the gap between "the toolset resolves" and
"everything that uses it still works" was about fifteen minutes of broken services.

**A server name is not configuration. It is a contract, and the contract is copied.**

## The Checklist

Do all of it in one window with the gateways down. Verifying only the first two gives a false
green.

| # | Place | How it breaks if missed |
| --- | --- | --- |
| 1 | `~/.hermes/config.yaml` — `mcp_servers` key, its `args` directory, and any `env` paths that embed the directory name | Server never starts |
| 2 | `~/.hermes/config.yaml` — `platform_toolsets.<platform>` list | Tools exist but are not exposed to that platform |
| 3 | `~/.hermes/mcp-servers/<name>/` — the directory itself | Everything above points at nothing |
| 4 | **`~/.hermes/profiles/<profile>/config.yaml`** — each profile carries its own full copy | Profile-scoped consumers fail while the default profile looks fine |
| 5 | **Wrapper scripts inside the server directory** (`bin/*`) with absolute self-references | Server starts, individual tools fail at exec time |
| 6 | **Deployed copies of controller scripts** outside the repo | Silent: the checked-in source is correct and the running code is not |
| 7 | `__pycache__` and `mcp_schema_cache.json` | Stale names resurface after everything else is right |

Items 4 to 6 are the expensive ones, because nothing in the first three hints that they exist.

## What Actually Bit

- `~/.hermes/profiles/jarvis/config.yaml` held its own `mcp_servers` block. The top-level config was correct, `hermes -t <new-name> -z` answered `OK`, and the messenger assistant still reported `Jarvis KakaoTalk MCP 서버가 활성화되지 않았습니다` because its controller reads `profile_dir / "config.yaml"` directly.
- `mcp-servers/<name>/bin/kakaocli-self-ssh` hard-coded the vendored binary's absolute path. The MCP server registered all 19 tools; `kakao-ai-chat` then failed every tick on `no such file or directory`.
- `scripts/hermes/messenger_assistant.py` and `scripts/hermes/kakao_ai_chat.py` pin the server name and tool prefix as module constants (`KAKAO_TOOLSET`, `KAKAO_MCP_TOOL_PREFIX`). Both are **deployed outside this repo**, so fixing the repo changes nothing on the host until they are copied over.
- A running daemon holds its config in memory. `kakao-ai-chat` kept using old paths after the fix until the previous instance released its lock.

## Verifying

Toolset resolution is necessary, not sufficient. The control is that the **old** name is now
rejected:

```bash
hermes -t <old-name> -z "hi"   # expect: ignoring unknown --toolsets entries
hermes -t <new-name> -z "Reply with exactly: OK"
hermes -p <profile> -t <new-name> -z "Reply with exactly: OK"
hermes doctor 2>&1 | grep -i toolset    # expect nothing
```

Then watch the consumers, not the config. Restart each dependent service and confirm its log
stops producing failures; a log that only records errors is healthy when it goes quiet. Give it
more than one tick interval before believing it.

Finally, sweep for survivors, excluding the things that should keep the old name:

```bash
grep -rl "<old-name>" ~/.hermes --include="*.yaml" --include="*.json" --include="*.py" \
  | grep -v "\.bak\|/backups/\|/recovery/\|state-snapshots\|/sessions/"
```

## What To Leave Alone

- Timestamped backups, `state-snapshots/`, `recovery/`, and session dumps. They record what was true then.
- `pyvenv.cfg`'s `prompt =` line. It is a shell label, not a path, and the interpreter resolves correctly without it.
- Vendored upstream sources and Apple toolchain triples such as `arm64-apple-macosx`.
