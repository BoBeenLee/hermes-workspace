---
type: Runbook
title: KakaoTalk Mac MCP
description: Runbook for wiring read-only KakaoTalk for Mac message access into the remote Hermes Agent through an MCP server.
resource: repo://hermes-workspace/knowledge/runbooks/kakaotalk-mac-mcp.md
tags: [hermes, kakaotalk, macos, mcp, remote-config]
timestamp: 2026-07-05T21:30:00+09:00
---

# KakaoTalk Mac MCP

This runbook records the reviewed path for read-only KakaoTalk for Mac message lookup through the default remote Hermes Agent on the `bobeen` macOS target.

KakaoTalk access is sensitive local data access. Treat every setup or config change here as `remote-config` work and finish as `review-required`.

## Installed Shape

The default remote host has a read-only KakaoTalk MCP server installed under:

```text
/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac
/Users/bobeenlee/.hermes/mcp-servers/kakaotalk-mac-message-list
```

The Hermes config has:

```yaml
mcp_servers:
  openhuman-kakaotalk-mac:
    command: /opt/homebrew/bin/uv
    args:
      - --directory
      - /Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server
      - run
      - python
      - mcp_server.py
    env:
      KAKAOTALK_MESSAGE_LIST_SKILL_DIR: /Users/bobeenlee/.hermes/mcp-servers/kakaotalk-mac-message-list
      KAKAOCLI_BIN: /Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor/kakaocli/.build/release/kakaocli
    enabled: true
platform_toolsets:
  cli:
    - antigravity-worker
    - terminal
    - openhuman-kakaotalk-mac
```

The `platform_toolsets.cli` entry is required. If the MCP server is configured but not listed for CLI, `hermes mcp test` can pass while `hermes -z` still cannot see KakaoTalk tools.

The Jarvis Discord profile must have the same MCP server and include `openhuman-kakaotalk-mac` in both `platform_toolsets.cli` and `platform_toolsets.discord`. A Discord request can otherwise reach Jarvis but still fail tool discovery or route only through non-KakaoTalk tools.

## Safety Rules

- Use read-only MCP tools only: `auth_status`, `list_chats`, `find_chat`, `list_new_messages_since`, `preview_messages`, and media listing/resolve tools.
- Do not use `ingest_messages_to_queue` unless queue ingestion has been explicitly requested and confirmed.
- Do not document or paste recovered KakaoTalk user IDs, SQLCipher keys, account IDs, phone numbers, DB paths, raw plist output, signed media URLs, or private message dumps.
- For smoke tests, return only tool names, safe target labels, counts, timestamps, and short previews needed to prove the path works.
- Prefer KST timestamps for Korean operators.

## Verification

Start from the workspace:

```bash
cd /Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace
bin/hermes-remote check-ssh
bin/hermes-remote status
```

Check MCP discovery:

```bash
ssh bobeen '/Users/bobeenlee/.local/bin/hermes mcp test openhuman-kakaotalk-mac'
```

Expected signal:

```text
Connected
Tools discovered: 9
kakaotalk_mac.auth_status
kakaotalk_mac.find_chat
kakaotalk_mac.preview_messages
```

Check Hermes CLI end-to-end lookup:

```bash
ssh bobeen '/Users/bobeenlee/.local/bin/hermes -z "카카오톡 MCP read-only 도구로 <대상> 채팅 최근 메시지 1건을 조회해줘. 전화번호 계정ID DB경로 secret 출력 금지. 결과에는 TOOL_USED, chat_id 대신 safe target, count, KST timestamp와 짧은 preview만 포함해."'
```

Expected signal:

```text
TOOL_USED: mcp_openhuman_kakaotalk_mac_kakaotalk_mac_find_chat, mcp_openhuman_kakaotalk_mac_kakaotalk_mac_preview_messages
count: 1
timestamp_kst: ...
preview: ...
```

When using the local wrapper, keep the toolset explicit so the prompt does not route to desktop control:

```bash
HERMES_RUN_TOOLSETS=openhuman-kakaotalk-mac \
  bin/hermes-remote run '카카오톡 MCP read-only 도구로 <대상> 채팅 최근 메시지 1건 조회. 전화번호 계정ID DB경로 secret 출력 금지. TOOL_USED, count, preview만.'
```

Without `HERMES_RUN_TOOLSETS`, `bin/hermes-remote run` defaults to `computer_use` on macOS targets and may try visible-window UI inspection instead of MCP.

## Auth Recovery

If `kakaotalk_mac.auth_status` returns `needs_user_id`, use the `kakaotalk-mac-message-list` skill's auth recovery flow. The known safe recovery pattern is:

1. Confirm KakaoTalk app, DB, and Full Disk Access state with safe diagnostics.
2. Build a temporary patched `kakaocli` under `/tmp/kakaocli-src` with a longer SHA-512 user ID recovery timeout.
3. Run verbose auth locally on the remote host, parse only success/failure, and do not paste the recovered user ID.
4. Store the recovered ID only in the remote runtime config used by the MCP server.
5. Re-run `auth_status`, `find_chat`, and `preview_messages`.

`sqlcipher` must be available for the bundled `kakaocli` binary:

```bash
ssh bobeen '/opt/homebrew/bin/brew list sqlcipher >/dev/null 2>&1 || /opt/homebrew/bin/brew install sqlcipher'
```

## Provider Note

On 2026-07-05, the previous default Groq provider returned `Request payload too large (413)` even for a tiny `hermes -z "say ok"` smoke test after tool schemas were loaded. The default model path was changed to the OpenRouter-compatible endpoint so normal Hermes CLI invocations can reach the KakaoTalk MCP tools.

The operator-visible status may show this as `Provider: Custom endpoint` with model `openai/gpt-oss-120b`. Do not record API keys in this repo.

## Discord Timeout Incident

On 2026-07-05, a Jarvis Discord request for general KakaoTalk messages failed with:

```text
all attempts to query the OpenHuman KakaoTalk service timed out
```

The root cause was a broad `list_new_messages_since` call over a large since-window. The first MCP call held the Jarvis session until Hermes' 300 second tool timeout, then follow-up calls such as `list_chats`, `auth_status`, and `find_chat` also timed out against the same wedged MCP connection. Direct auth and exact MCP calls still worked, so the failure was not KakaoTalk DB authentication.

The deployed fix bounds the read path:

- `KAKAOTALK_MCP_DEFAULT_CHAT_LIST_LIMIT` defaults to `100`.
- `KAKAOTALK_MCP_DEFAULT_MESSAGE_LIMIT_PER_CHAT` defaults to `30`.
- `KAKAOTALK_MCP_KAKAOCLI_TIMEOUT_SECONDS` defaults to `25.0`.
- `KAKAOTALK_MCP_SCAN_BUDGET_SECONDS` defaults to `45.0`.
- `list_new_messages_since` returns partial results with `partial`, `truncated_reason`, `chat_count_requested`, `chat_count_scanned`, and `elapsed_seconds` instead of running until the outer Hermes timeout.

If this recurs, inspect the Jarvis logs for the first timed-out MCP call before chasing later retry failures. Prefer a constrained prompt such as "recent 5 messages" or a target chat lookup. For broad scans, a successful direct MCP smoke signal should complete in seconds and include bounded metadata, for example:

```text
ok=true, requested=100, scanned=<n>, partial=false, elapsed=<seconds>
```

## Change Evidence

Known 2026-07-05 remote backups created during setup:

```text
/Users/bobeenlee/.hermes/config.yaml.bak-kakaotalk-mcp-20260705201357
/Users/bobeenlee/.hermes/config.yaml.bak-kakaotalk-cli-toolset-20260705202458
/Users/bobeenlee/.hermes/config.yaml.bak-openrouter-default-<timestamp>
```

Final verification showed:

- `hermes mcp test openhuman-kakaotalk-mac` discovered the KakaoTalk tools.
- Default `hermes -z` successfully used `find_chat` and `preview_messages` for a target chat.
- `HERMES_RUN_TOOLSETS=openhuman-kakaotalk-mac bin/hermes-remote run ...` successfully used the MCP path instead of desktop control.
- Gateway was restarted and `bin/hermes-remote status` showed the `openhuman-kakaotalk-mac` MCP process running.
- Jarvis Discord recovery after the timeout fix returned recent KakaoTalk message previews and posted the corrected result back to the failed Discord thread.
