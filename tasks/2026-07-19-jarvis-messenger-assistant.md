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

## Direct-room chat ID allowlist

- The controller now requires a non-empty numeric `allowed_chat_ids` config
  list and fails closed when it is absent or invalid. Production is restricted
  to adapter chat ID `128426307555607` (display name `이보빈`).
- The allowlist is checked before direct-room discovery and candidate
  buffering, again before buffered classification, and finally before every
  automatic, approved, or correction send. Messages from other rooms are
  ignored even when `is_from_me=true`; stale Discord cards cannot bypass the
  final send guard.
- Existing non-allowed room buffers are pruned, and pending/held cards for
  non-allowed rooms are invalidated. Production inspection found no such
  buffers or live pending cards after deployment.
- The installer accepts repeatable `--allowed-chat-id`, preserves an existing
  non-empty list on later upgrades, backs up the previous config, and writes
  config version 2.
- Local checks: Python compilation passed; 36 unit tests passed, including
  allowed/manual-outgoing buffering, non-allowed manual-outgoing rejection,
  empty/invalid allowlist rejection, and pre-MCP send rejection; OKF validation
  and `git diff --check` passed.
- Installed controller SHA-256:
  `ea0bc2030693424dfee4505ab9f59a2bdfc17217cd184b71850cc7a0aa5c09df`.
  Backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-chat-allowlist-20260719-235318`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json.bak-chat-allowlist-20260719-235318`.
- Remote controller `--check` passed with `allowed_chat_ids=true`. The dedicated
  Discord listener reconnected as PID `58474`; Jarvis gateway PID `56537` was
  not restarted. Scheduled execution `095d724d70e44e8190039c4dd87fa549`
  completed `ok`, advanced the Kakao poll cursor to 23:55:46 KST, retained only
  allowed room state, and left the assistant enabled.
- Branch/worktree: `main` at
  `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`.
- Completion mode remains `review-required` because the recurring controller
  and remote routing configuration changed.

## Confidence-based automatic replies

- The content gate now uses the primary model's reported confidence only:
  `0.80` and above sends automatically, while lower or non-finite values create
  an approval card. Semantic risk flags remain visible in Discord audit cards
  but no longer independently block sending.
- The classifier interface is `intent`, `reply_kind`, `reply`, `summary`,
  `reason`, `confidence`, and `weather_location`. Missing required details are
  answered with an automatic clarification when confidence passes the gate.
- A location-free weather question asks for the region. A later place reply is
  recovered from recent same-room context, geocoded through Open-Meteo, and
  resolved through a second current-forecast request. Both requests use one
  exact verified Jarvis terminal call and raw session tool output.
- Ambiguous regions, stale or malformed weather, changed terminal commands,
  fallback models, empty replies, and uncertain Kakao sends still fail closed.
- `assistant_status` always replaces the draft with the friendly fixed response
  and exposes no process, Discord, MCP, polling, model, or token details.
- Local regression suite: 33 tests passed, including the `0.79`/`0.80`
  boundary, all semantic audit flags, missing-location follow-up, Seoul weather,
  ambiguous/stale weather, exact terminal evidence, status redaction, and the
  Hermes 0.18.2 JSON gateway PID record.
- Read-only production smoke checks returned the expected primary model schema:
  missing-location weather confidence `0.85` and assistant-status confidence
  `0.92`. The follow-up context ending in `서울` recovered
  `intent=weather`, `weather_location=Seoul`, and confidence `0.82`. A verified
  Seoul lookup returned fresh Open-Meteo data without any KakaoTalk send.
- Installed controller SHA-256:
  `1578386107103765fda85464dac9dfe2659968001f364e5b90cf3476e53e1a3e`.
  Backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-confidence-auto-20260719-233334`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-json-gateway-pid-20260719-234011`.
- The initial Discord listener restart reported connected. The
  first post-deployment cron execution `c7af106999ca4fd694e8c0b50218301a`
  completed `ok` at 23:36:38 KST, advanced both Kakao cursors to 23:36:13,
  kept the assistant enabled, and added no failures.
- A concurrent KakaoTalk MCP `validated-send-id` deployment independently ran
  `hermes --profile jarvis gateway restart`, sending SIGTERM at 23:38:06 and
  again at 23:41:03. This controller deployment did not invoke either restart;
  launchd ultimately restored the gateway as PID `56537`.
- Hermes 0.18.2 stores `gateway.pid` as JSON instead of the previous plain PID.
  The controller's old parser returned `invalid`, so a red regression test was
  added and the parser now supports both formats. After the corrected script
  was deployed, listener PID `56361` connected and correctly changed the
  assistant to disabled. Cron execution `24b4e852bad44bb09c2a37ca0eab9a7a`
  then completed `ok`, recorded gateway identity PID `56537`, and kept the
  assistant disabled. The allowed user must issue `메신저 시작` in Discord to
  establish a fresh baseline.
- Completion mode remains `review-required` because the automatic-send policy
  and recurring controller deployment are materially changed.

## Jarvis-direct MCP refactor

- The two-minute cron remains the only Kakao polling trigger. It wakes the
  deterministic controller, which now delegates every Kakao read/send to a
  Jarvis one-shot restricted to `openhuman-kakaotalk-mac`.
- `JarvisKakaoAgent` is the single Kakao seam. The controller no longer opens
  MCP stdio sessions itself and no longer contains a CuaDriver send fallback.
- Each operation requires the primary Jarvis model/provider and verifies one
  exact namespaced MCP tool call, required tool arguments, and the raw tool
  result from the same Hermes session database before using it.
- Live read-only evidence:
  - auth session `20260719_225230_ad040a` called `auth_status` once and reported
    read auth ready;
  - preview session `20260719_225539_f7772e` called `preview_messages` once and
    returned 20 events;
  - poll session `20260719_225611_05683c` called
    `list_new_messages_since` once for a five-minute interval, completed the
    adapter scan in about 12 seconds, and was not partial.
- Result sizes are bounded because the previous 50-message/4,000-character
  preview produced a 115 KB tool response that Hermes truncated. Truncated or
  malformed results now fail closed.
- Send dry-run session `20260719_225940_c3c65b` proved the direct Jarvis MCP
  route and preserved the adapter's exact `kmsg_chats_timeout` failure without
  sending a message. No UI fallback or duplicate actual send was attempted.
- Deployed controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-jarvis-agent-mcp-20260719-230218`.
- The first confirmed scheduled production run completed at 23:05:34 KST.
  Session `20260719_230510_842530` contains four records and exactly one
  `list_new_messages_since` MCP tool result; the production scan cursor advanced
  from 23:02:09 to 23:05:09 KST with zero added failures. The listener restarted
  as PID `51620`; the Jarvis gateway was not restarted.
- Completion mode remains `review-required` because this changes the recurring
  controller and remote listener deployment.

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
