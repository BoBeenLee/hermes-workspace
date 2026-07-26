---
type: Task
title: KakaoTalk approval-card conversation binding
status: review-required
date: 2026-07-26
---

# KakaoTalk approval-card conversation binding

## Lifecycle

- Task type: `ops-change` and `remote-config`
- HIL status: completed in the Codex task; no Discord thread id
- Approved goal: capture the read-side conversation and kmsg send destination binding when an approval card is created, persist it with the card, and reuse that exact binding for an approved or edited reply
- Non-goals: no reply-time recent-chat rediscovery, no legacy-card backfill by name, no automatic retry, no group-room send, and no authentication or recurring-schedule change
- Completion mode: `review-required`

## Workspaces

- Hermes branch: `codex/kakao-send-fallback-20260726`
- Hermes worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace/.worktrees/kakao-send-fallback-20260726`
- KakaoTalk MCP branch: `codex/verified-direct-send-fallback-20260726`
- KakaoTalk MCP worktree: `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-skill/.worktrees/verified-direct-send-fallback-20260726`
- Remote target: `bobeen`

## Changes

- Approval-card creation performs a no-send MCP dry run while the conversation is current.
- The MCP returns a versioned binding containing:
  - the read-side direct chat ID;
  - the normalized display name; and
  - the resolved kmsg send chat ID.
- If multiple recent chats have the same display name, the latest incoming message text is used as an exact anchor. A missing or ambiguous anchor fails closed and no approval card is created.
- The controller persists the binding in the pending-card record.
- Approval and edited replies pass the stored binding back to the MCP.
- A bound send validates the stored read chat ID and display name, skips the recent-chat scan entirely, and invokes kmsg with only the bound send chat ID.
- A missing, malformed, or mismatched binding fails before send. Legacy cards are never backfilled by room name and remain unusable for sending.
- Read-back verification still uses the read-side chat ID and the existing one-attempt idempotency boundary.

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
- Conversation-binding backups:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-conversation-binding-20260726-231220`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-conversation-binding-20260726-231220`
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-binding-schema-20260726-231336`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-binding-object-20260726-231437`
- The poller and Discord listener were restarted. The Jarvis gateway and schedule were not changed.

## Verification

- KakaoTalk MCP: `python3 -m unittest discover -s tests -p 'test_*.py'` — 135 passed
- Hermes controller: `python3 -m unittest tests/test_messenger_assistant.py` — 113 passed
- `python3 scripts/hermes/validate_okf.py`
- `bin/hermes-remote check-ssh`
- `bin/hermes-remote status`
- Remote controller `--check`
- Remote Python syntax checks for the installed MCP and controller
- Both messenger-assistant launchd services reported `running`
- A remote negative binding probe returned:
  - `error=conversation_binding_mismatch`
  - `send_attempted=false`
  - `message_sent=false`
  - `scan_limit=0`
- Read-back confirmed zero outgoing matches for the negative probe text.

## Live validation result

The pre-existing `이보빈` approval card was created before conversation bindings existed and is now invalidated. It was not resent or backfilled. A newly generated card is required before an approval reply can be sent through the binding-only path.

No additional actual KakaoTalk send was attempted during this binding deployment.

## Source ledger

None; this was a code and remote-operations task using local repositories and direct remote diagnostics.
