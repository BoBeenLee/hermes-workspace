---
type: Task
title: KakaoTalk verified direct send fallback
status: review-required
date: 2026-07-26
---

# KakaoTalk verified direct send fallback

## Lifecycle

- Task type: `ops-change` and `remote-config`
- HIL status: completed in the Codex task; no Discord thread id
- Approved goal: allow a recent-chat miss to fall back to a uniquely verified human 1:1 read-side `chat_id`, without enabling an unverified or group-room fallback
- Non-goals: no global unverified fallback, no automatic retry, no group-room send, and no authentication or recurring-schedule change
- Completion mode: `review-required`

## Workspaces

- Hermes branch: `codex/kakao-send-fallback-20260726`
- Hermes worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace/.worktrees/kakao-send-fallback-20260726`
- KakaoTalk MCP branch: `codex/verified-direct-send-fallback-20260726`
- KakaoTalk MCP worktree: `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-skill/.worktrees/verified-direct-send-fallback-20260726`
- Remote target: `bobeen`

## Changes

- The KakaoTalk MCP accepts a target fallback after a successful recent-chat scan misses only when:
  - the requested `chat_id` is numeric;
  - the normalized display name matches exactly;
  - the evidence includes `NTUser.directChatId`;
  - `direct_chat_kind` is `human`; and
  - the name resolves uniquely to the requested `chat_id`.
- A read lookup error, 100-result truncation, ID mismatch, non-human result, ambiguous result, missing target, or recent-scan error still fails closed.
- MCP results now distinguish destination rejection before the command from a failed `kmsg send` command with `send_attempted` and `failure_stage`.
- The controller reports a confirmed pre-send destination rejection separately from post-attempt delivery uncertainty and leaves the approval card pending.
- A time-sensitive idempotency test now freezes its clock so the seven-day context cutoff cannot make it expire.

## Remote deployment

- Loaded MCP file:
  `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py`
- Installed controller:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py`
- Initial backups:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-verified-direct-fallback-20260726-215642`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-verified-direct-fallback-20260726-215642`
- Failure-stage backups:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-send-stage-20260726-220516`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-send-stage-20260726-220516`
- The poller and Discord listener were restarted. The Jarvis gateway and schedule were not changed.

## Verification

- `python3 -m unittest tests.test_kakaotalk_mcp_server tests.test_kakaotalk_observe`
- `python3 -m unittest tests.test_messenger_assistant`
- `python3 scripts/hermes/validate_okf.py`
- `bin/hermes-remote check-ssh`
- `bin/hermes-remote status`
- Remote controller `--check`
- Remote Python syntax checks for the installed MCP and controller
- Both messenger-assistant launchd services reported `running`
- MCP dry-run for `이보빈` and `128426307555607` returned:
  - `ok=true`
  - `chat_id_validated=true`
  - `destination_resolved_by=read_side_human_direct_after_recent_miss`
  - `send_chat_id=""`
  - `message_sent=false`

## Live validation result

One approved actual attempt was made for `[메신저 비서] 어떤거 말이야`. Exact read-back found no outgoing match, so no retry was attempted and the original approval remains `pending`.

A read-only traced `kmsg read "이보빈"` reproduced the remaining lower-layer failure:

- the chat-list search field accepted the query;
- both fast and expanded scans found zero candidates; and
- `kmsg` returned `SEARCH_MISS`.

The verified MCP fallback therefore works, but the installed `kmsg` cannot currently open a human direct chat that is absent from the chat tab's exposed search results. Fixing that requires a separately approved `vendor/kmsg` friend-list or other verified UI-opening fallback, which is outside this task's approved MCP-and-controller scope.

## Source ledger

None; this was a code and remote-operations task using local repositories and direct remote diagnostics.
