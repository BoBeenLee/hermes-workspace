# Jarvis Messenger Assistant

- Task type: `remote-config` and `ops-change`
- HIL status: completed in the originating Codex task
- Goal: add the agreed KakaoTalk messenger-assistant role to the existing
  remote Jarvis profile without creating another profile or Discord bot
- Target: `/Users/bobeenlee/Workspaces/hermes-workspace` and
  `/Users/bobeenlee/.hermes/profiles/jarvis`
- Branch: `codex/jarvis-messenger-assistant`
- Local worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Expected remote changes: private Discord control channel, Jarvis `.env` ignore
  entry, managed `SOUL.md` section, controller/config/state files, two-minute
  Kakao-only script cron, realtime Discord launchd listener, Jarvis gateway
  restart
- Secret handling: existing Discord token is read only on the remote host;
  KakaoTalk login values are entered directly by the user through `kmsg`; no
  secret is handled by Jarvis or committed
- Completion mode: `review-required`

## Checks

- Private Discord control surface: private thread `메신저-비서`
- Cron job: `643add69262e`, active, `every 2m`, script-only/no-agent
- Realtime Discord service:
  `~/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-discord.plist`,
  launchd `running`, Gateway `connected`, `RunAtLoad` and `KeepAlive` enabled
- Remote backups:
  - `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak-messenger-assistant-20260719-195358`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/SOUL.md.bak-messenger-assistant-20260719-195358`
- Local checks:
  - `python3 -m py_compile scripts/hermes/messenger_assistant.py scripts/hermes/install_messenger_assistant.py`
  - `python3 -m unittest tests/test_messenger_assistant.py` — 15 passed
  - `python3 scripts/hermes/validate_okf.py` — passed
  - `git diff --check` — passed
- Remote checks:
  - controller `--check` — passed
  - Jarvis `config check` — config version 33 valid
  - controller/config/state permissions — user-only
  - Jarvis gateway — supervised by launchd after restart
  - Discord gateway — private control surface created; dedicated realtime
    listener added so control commands are not cron-driven
  - KakaoTalk read authentication — passed; 13 direct rooms detected
  - KakaoTalk send dry-run — fail-closed until the user completes interactive
    `kmsg auth login`;
    no external KakaoTalk state changed
  - cron direct and builtin runs — completed after correcting the named-profile
    script location to `~/.hermes/profiles/jarvis/scripts/`
  - cron separation — manual cron run did not advance the Discord command
    cursor; Discord is consumed only by the realtime listener
  - `인증 완료` regression — original production repro changed from
    `RED_NO_RESPONSE_TO_AUTH_COMPLETE` to `GREEN_RESPONSE_PRESENT`
- `kmsg` readiness regression — authenticated `kmsg chats --json` returns a
  `{chats, count}` envelope, not a top-level list; the controller now accepts
  both supported shapes and production changed from
  `RED_DICT_ENVELOPE_REJECTED` to a successful read/send-ready Discord notice
- Direct-room regression — the read adapter reports a real 1:1 room through
  `NTUser.directChatId` while its visible-chat `member_count` is `1`. The
  controller no longer treats `member_count == 2` as 1:1 and now requires the
  adapter's matching direct-room evidence for both baseline summaries and
  subsequent polling.
- Direct-room tests — the production-shaped `member_count=1` direct room changed
  from omitted to buffered, while a `member_count=2` room without direct-room
  evidence changed from buffered to rejected; the full suite passes 17 tests.
- Installed controller — local and remote SHA-256 matched after deployment;
  the live adapter recognized the diagnosed target room as direct.
- Controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-direct-room-20260719-204525`
- Cron backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/cron/jobs.json.bak-every-2m-20260719-204525`
- Cron update — job `643add69262e` is active at `every 2m`; its first
  post-deployment execution completed successfully and the next run was
  scheduled two minutes later.
- Realtime listener — restarted after controller deployment and returned to
  launchd `running` state without restarting the Jarvis gateway.
- Persisted controller state after the direct-room deployment — `enabled: true`,
  zero pending approvals, zero buffered rooms, and a successful Kakao poll at
  `2026-07-19T20:45:28+09:00`.
- User-authored outgoing candidates — `is_from_me=true` messages now enter the
  same candidate buffer as incoming messages. Messages beginning with
  `[메신저 비서]` remain excluded at polling and replay time so automatic,
  approved, and corrected replies cannot trigger a self-reply loop.
- Stable direct-room lookup — polling now reads all `NTUser.directChatId` values
  in one adapter DB query, avoiding the `find_chat` preview-followup guard while
  retaining fail-closed direct-room matching.
- Outgoing-candidate tests — the targeted regressions changed from RED to GREEN
  and the full suite passes 18 tests, including manual outgoing inclusion and
  assistant-prefixed outgoing exclusion.
- Outgoing-candidate controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-from-me-candidate-20260719-210100`
- Outgoing-candidate state backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-from-me-candidate-20260719-210100`
- Live outgoing-candidate verification — the latest pre-deployment manual
  outgoing message was registered once, consumed by direct cron execution
  `eb5e6d7dc09a43c08c07883f305aaddf`, recorded as processed, and routed to one
  pending Discord approval card with zero failures and no automatic send.
- MCP-only KakaoTalk path — auth checks, direct-room lookup, recent-message
  polling, baseline reads, previews, send dry-runs, and sends now call the
  Hermes-configured `openhuman-kakaotalk-mac` MCP tools. The controller no
  longer imports the adapter or invokes `kakaocli`, `kmsg`, `pgrep`, or
  `open -a KakaoTalk` directly.
- Send resolution fix — a target-name dry-run now resolves `send_chat_id`, a
  second MCP dry-run validates that exact ID, and actual send is attempted only
  once. The previous requirement that the first name-based dry-run already have
  `chat_id_validated=true` rejected valid unique targets.
- MCP live verification — the existing pending room returned
  `NTUser.directChatId` evidence through MCP, the two-stage send dry-run passed
  without an actual send, and direct cron execution
  `d23181dc6efb401a81ac6346a7b3cf49` advanced the Kakao poll cursor.
- Scheduled verification — builtin execution
  `74fe385d21cc45bcb0317b097c0d1015` completed on the two-minute schedule and
  advanced both the poll and scan cursors while leaving the assistant enabled.
- MCP controller backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-mcp-protocol-20260719-211521`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-mcp-poll-20260719-211720`.
- Human review/action still required:
  - reply `승인` again to the still-pending Discord card if the draft should be
    sent through the corrected MCP path; deployment verification performed no
    actual KakaoTalk send
- Source ledger: Context7 `/discord/discord-api-docs` for Discord Gateway
  MESSAGE_CREATE, heartbeat/resume, and message-content intent requirements;
  Context7 `/nousresearch/hermes-agent` plus installed v0.18.2 CLI help for
  `hermes cron edit <job_id> --schedule "every 2m"`
- Completion mode: `review-required`
