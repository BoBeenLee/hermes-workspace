# Jarvis Messenger Assistant

## Unread-only reply triggers and speaker-attributed context

- Task type: `ops-change` and `remote-config`.
- HIL status: skipped; the user directly requested the diagnosed TO-BE fix and
  clarified that group-derived context must distinguish each counterparty.
- Root causes reproduced:
  - user-authored `is_from_me=true` messages were eligible reply candidates;
  - the unread-first selector appended every remaining incremental message,
    including already-read history;
  - after a stalled cursor recovered, that backlog could be drafted as one
    turn with operator-authored links.
- The reply-trigger seam now accepts only current unread messages from the
  other party. Read messages and every operator-authored message are excluded.
- Unread messages more than five minutes old are marked processed without
  automatic reply and summarized to Discord without copying their text.
- A manual operator reply invalidates pending drafts and cancels buffered
  incoming messages at or before the manual reply timestamp. A later unread
  incoming message in the same scan remains eligible.
- `recent_context` still includes both sides, but every event now carries
  `speaker_role`, `speaker_name`, and `speaker_key`. Operator events use
  `speaker_key=operator`; each named counterparty uses
  `speaker_key=other_party:<name>`, preserving multiple participants in
  group-derived context. The adapter currently exposes names, not stable sender
  IDs.
- The intent and drafting prompts explicitly constrain `new_turn` to
  `other_party` events and forbid attributing operator links or statements to
  the other party.
- The exact production-shape replay now returns no candidates for the
  operator's outbound messages or Kim Seohyun's already-read historical
  incoming message.
- Local verification: 75 controller tests pass, including unread-only,
  five-minute stale, operator-cancels-buffer, and multi-counterparty context
  regressions.
- Remote backups:
  - `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-speaker-unread-20260726-195244`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-speaker-unread-20260726-195244`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/SOUL.md.bak-speaker-unread-20260726-195244`
- The controller and managed SOUL block were updated without rewriting the
  existing config or launchd plists. Installed controller SHA-256 is
  `9a0fac5c504e4ecd6655adf9268122294c780c0d660198baffb2833eeede2905`.
- launchd returned the known transient bootstrap error 5 immediately after
  bootout; retrying the two valid plists succeeded. The Discord listener and
  poller run as PIDs `39491` and `39493`; Jarvis gateway PID `17319` was not
  restarted.
- Production verification at `2026-07-26T10:53:57+00:00`: enabled, 30-second
  polling, successful cursor advance, no poll error, no buffer, no pending
  approval, zero failures, and the automatic-send count remained at the
  pre-fix value of one. No additional KakaoTalk message was sent during
  deployment verification.
- Completion mode: `review-required` because the recurring remote controller
  behavior changes.

## Deterministic MCP adapter and live polling controls

- Task type: `ops-change` and `remote-config`.
- HIL status: skipped; the user directly requested pulling the latest `main`
  and deploying the agreed TO-BE messenger workflow.
- `git pull --ff-only origin main` confirmed local `main` was already current
  at `2891e06` before this change.
- Root cause addressed: KakaoTalk reads and sends used GPT-5-nano as a
  deterministic RPC proxy. Production history showed repeated zero-tool,
  argument, JSON, and model/provider validation failures before the adapter was
  reached.
- `KakaoMcpAdapter` is now the single Kakao seam. It loads the existing Jarvis
  MCP server definition, uses MCP Python SDK 1.26.0 over SDK-managed stdio,
  calls one exact `kakaotalk_mac.*` tool with controller-owned arguments, and
  normalizes structured results. GPT remains only for intent routing, drafting,
  typed-memory extraction, and the existing allowlisted public-data workflow.
- Incremental scans request and prioritize unread metadata. The first
  successful scan also supplies the start summary, eliminating the former
  second seven-day baseline scan. Cursor and room buffers are persisted before
  classification, drafting, link lookup, or sending.
- Discord controls now cover `폴링 상태`, `폴링 주기 <N초|N분>`,
  `폴링 즉시실행`, `폴링 일시정지`, and `폴링 재개`. The persistent poller
  reloads these durable controls while waiting.
- Only links supplied by the other party in the current turn are opened in the
  isolated browser. Operator-sent links remain textual context and no longer
  trigger redundant browser calls.
- Pre-deployment direct-MCP smoke called `list_new_messages_since` without a
  model one-shot and returned `ok=true`, one room, and `partial=false`; no
  message text was printed by the smoke check.
- Remote backups:
  - controller and state baseline:
    `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-direct-mcp-20260726-193040`
    and
    `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-direct-mcp-20260726-193040`;
  - installer-managed SOUL, config, and launchd backups use timestamp
    `20260726-193047`;
  - intermediate controllers:
    `messenger_assistant.py.bak-single-scan-20260726-193236` and
    `messenger_assistant.py.bak-early-save-20260726-193714`.
- The first installer attempt applied the controller and poller but the Discord
  listener bootstrap returned transient launchd error 5. The valid plist was
  bootstrapped again successfully; the final poller/listener PIDs are `34353`
  and `34491`. Jarvis gateway PID `17319` was not restarted.
- Final production evidence at `2026-07-26T10:37:15+00:00`: enabled, 30-second
  interval, not paused, latest attempt/success/scan cursors equal, no poll
  error, no buffered or pending room, and connected Discord listener. No
  `Jarvis KakaoTalk MCP execution step` one-shot remained.
- The first direct-MCP production cycle found one eligible turn and completed
  one automatic reply under the existing confidence/send policy. It recorded
  zero failures.
- Verification: Python compilation, 71 controller tests, OKF validation,
  `git diff --check`, remote controller `--check`, direct read-only MCP smoke,
  launchd process checks, installed SHA-256 match, SSH check, and final Hermes
  status.
- Completion mode: `review-required` because recurring polling and automatic
  send execution changed.

## Unread-first polling and live interval commands

- HIL status: skipped; the user directly requested unread-first processing and
  command-configurable polling on the default remote Mac.
- Incremental KakaoTalk scans now request unread metadata, process rooms and
  messages with current unread items first, deduplicate unread/new overlap,
  and exclude unread items older than the active scan boundary from automatic
  reply processing.
- The private Discord control channel now accepts `폴링 주기`,
  `폴링 주기 45초`, and `폴링 주기 2분`. The durable interval is constrained
  to 5 seconds through 60 minutes, appears in `메신저 상태`, and is re-read by
  the running poll loop without a launchd plist rewrite.
- A Discord command arriving during a long Kakao scan now waits for the
  controller lock and reloads durable state after acquiring it. This prevents
  an interval command from being dropped or overwriting newer poll state.
- Local verification: all 68 messenger-assistant tests passed; Python
  compilation, OKF validation, and `git diff --check` passed.
- Remote controller backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-unread-poll-20260726-191122`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-command-lock-20260726-191250`.
  State backups use the same suffixes under
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json`.
- Deployed controller SHA-256:
  `29634dfa22ebfbd56175c28d2af53e535132b37f87639dc80c9a455310a02ec6`.
  The poller and Discord listener restarted as PIDs `27219` and `27182`;
  Jarvis gateway PID `17319` remained unchanged.
- Remote verification confirmed the persisted 30-second default, connected
  Discord listener, and `include_unread=true` in the active Kakao scan. No live
  KakaoTalk message was sent.
- Pre-existing operational issue: post-deployment baseline attempts still
  failed because the session verifier reported zero recorded
  `list_new_messages_since` calls even when an actual Kakao MCP child process
  was observed. A read-only SQLite `PRAGMA quick_check` then confirmed many
  invalid and duplicate page references in the Jarvis profile `state.db`.
  The unread/interval configuration is deployed, but successful message
  processing remains blocked by this separate session-database corruption.
  Repair was not attempted because it requires a separately reviewed gateway
  stop, full database backup, recovery, and session verification.
- Completion mode: `review-required` because recurring automation behavior and
  the remote controller changed.

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

## Start-baseline pending replay guard

- HIL status: skipped; the user directly requested the diagnosed replay guard.
- Root cause: `메신저 시작` created a fresh scan baseline but also restored
  every pending or held approval card to `room_buffers` without comparing its
  `latest_at` timestamp with that baseline. On 2026-07-26 this replayed
  2026-07-20 entity IDs and allowed one old draft to reach an actual
  `dry_run=false` send.
- Start now invalidates pending or held cards first and restores them only when
  `latest_at` parses successfully and is at or after the newly created
  baseline. Missing, malformed, and pre-baseline timestamps fail closed without
  re-entering the automatic-reply buffer.
- The focused regression reproduced the old buffer restoration before the
  change and passes afterward. The full controller suite passes 63 tests;
  Python compilation, OKF validation, and `git diff --check` also pass.
- Remote controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-start-baseline-20260726-165826`.
  The installed controller SHA-256 is
  `e0103f717b514dff81fbeb63da04ce0cf409ad77d48bb2b38a85bb739b38205f`.
- Only the messenger poller and Discord listener restarted, as PIDs `12000`
  and `12001`. Jarvis gateway PID `2255` remained unchanged during deployment.
  The assistant remained enabled with zero buffered rooms, and the first
  post-restart poll advanced both cursors to `2026-07-26T07:58:46+00:00`.
- A separate external operation subsequently restarted the Jarvis gateway as
  PID `12323`. This deployment did not request that restart. The controller's
  gateway-identity guard correctly changed the assistant to disabled with zero
  buffered rooms; the user must explicitly issue `메신저 시작` to establish a
  new baseline and resume automatic replies.
- No live KakaoTalk message is sent during verification.
- Completion mode: `review-required` because the recurring automatic-reply
  controller behavior changed.

## Non-human direct-chat exclusion

- HIL status: skipped; the user explicitly requested that non-human KakaoTalk
  channels be excluded from messenger processing.
- Root cause: `NTUser.directChatId` proves a one-to-one-shaped room but does not
  prove the peer is a human. Business and AlimTalk channels can have the same
  direct-chat identifier and were accepted by the previous policy.
- The KakaoTalk adapter now joins `NTUser` and `NTChatRoom` metadata and returns
  `direct_chat_kind` plus non-sensitive classification reasons. Non-zero
  `userType`, business/public-institution verification, AlimTalk, bot, BizChat,
  or an explicitly non-writable channel classifies the destination as
  `non_human`.
- Jarvis now requires both the exact `NTUser.directChatId` source and
  `direct_chat_kind=human`. A versioned final-send guard invalidates old cached
  direct-room evidence, so a stale approval or buffered turn cannot bypass the
  new policy.
- Regression coverage proves that the observed business/AlimTalk shape is
  rejected, the known human shape remains accepted, and legacy direct caches
  fail closed.
- Live verification classified the business/AlimTalk room as `non_human` with
  `user_type:1`, `verification_type:BUSINESS`, `alimtalk`, and `not_writable`;
  the known human room remained `human`. The installed controller reported the
  non-human room as `bc_sendable=false`.
- Controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-nonhuman-filter-20260726-164643`.
  Adapter backups:
  `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/observe.py.bak-nonhuman-filter-20260726-164643`
  and
  `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/adapters/kakaotalk/observe.py.bak-nonhuman-filter-20260726-164643`.
- Installed SHA-256 values are
  `b14e334619e82684cde2dea0af7945e080d9424a12a6890f092b1c55cefd569d`
  for the controller and
  `bc3b5835e82d5d73b5dba1e6224b20a6a27476d7e0a4d6a5857fa5b13ee7d7ea`
  for the adapter.
- All 62 messenger-controller tests and 104 KakaoTalk adapter/MCP tests passed.
  Python compilation, OKF validation, `git diff --check`, live controller
  `--check`, SSH validation, and Hermes status checks passed.
- KakaoTalk adapter source commit:
  `5bd8b10 fix: exclude non-human direct chats` on `main`, cherry-picked from
  the reviewed `92bb357` branch commit.
- Only the messenger poller/listener restarted, as PIDs `9048` and `9046`.
  Jarvis gateway PID `2255` remained unchanged, the assistant remained enabled,
  and the Discord listener reconnected.
- Completion mode: `review-required`.

## Expected-tool call counting

- HIL status: completed in the originating Codex task; Discord thread id: none.
  The user requested that mixed-tool Jarvis sessions be validated and reported
  by the requested `send_message` call count rather than the total number of
  tool calls in the session.
- The session verifier now filters assistant calls and tool-result rows by the
  requested tool name. Unrelated calls such as `web_fetch` no longer make a
  single `send_message` look like a duplicate, while zero or duplicate sends
  still fail closed.
- Count mismatches now report the concrete operation and both counts, for
  example `send_message 호출 수 0회, 결과 수 0회입니다(각각 1회 필요)`.
  Exact send arguments and the matching MCP result payload remain required.
- Regression coverage includes an unrelated fetch plus one send, zero sends,
  and two sends. All 60 messenger-assistant tests pass; Python compilation,
  OKF validation, and `git diff --check` also pass.
- Remote controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-send-count-20260720-135159`.
  The deployed local and remote controller SHA-256 is
  `86802250813f7e0a2ed16c1b3927a5c4c701fba7df7d42499ddd173bfb3de183`.
- The 80-second poller and Discord listener restarted successfully as PIDs
  `5865` and `5867`; controller `--check` passed every check. The first
  post-restart poll reached the existing, separate Jarvis model/provider guard
  and logged `승인된 Jarvis 모델이 KakaoTalk MCP를 호출하지 않았습니다`.
  That provider mismatch is not caused or fixed by the call-count change.
- The pre-existing dirty files in the remote canonical workspace were left
  untouched. Completion mode: `review-required`.

## Intent router, explicit dialogue state, and typed memory

- HIL status: completed in the originating Codex task; Discord thread id: none.
  The user approved the architectural fix after an `이보빈` turn containing
  `비빔밥..?` was incorrectly answered with old `하남` weather information.
- Production trace confirmed that the current turn was exactly `비빔밥..?`,
  while the model route selected `weather` and `Hanam` by prioritizing recent
  context and the legacy `weather_location` memory. The weather resolver then
  produced the unrelated automatic-send card.
- `ConversationPolicy` now routes intent from only the current turn and
  explicit dialogue state. Recent context and memory are supplied only to a
  second reply-drafting call after intent `other` is locked. Ungrounded weather
  routes and weather content smuggled through a locked non-weather draft are
  held for approval before any Open-Meteo lookup or automatic send.
- State schema v2 has a separate, expiring dialogue-state map. Missing-location
  weather questions create `pending_intent=weather_location` for 15 minutes;
  completion, expiry, or another completed intent clears it.
- Memory schema v2 accepts only `profile`, `preference`, `relationship`, and
  `constraint` facts that cite entity IDs from the current turn. The legacy
  `weather_location`, `weather_location_hanam`, and untyped label entries were
  removed during migration; production memory is now empty.
- Local verification: all 55 controller tests passed, including the exact
  bibimbap regression, explicit weather follow-up, router/drafter separation,
  intent-lock enforcement, typed-memory provenance, and v1 migration. Both
  Python entry points compiled, installer help parsing passed, OKF validation
  passed, and `git diff --check` passed.
- Remote backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-conversation-policy-20260720-013950`,
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-conversation-policy-20260720-013950`,
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/memory.json.bak-conversation-policy-20260720-013950`.
  The final boundary-deepening controller update was additionally backed up at
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-conversation-policy-v2-20260720-014321`.
  Deployed SHA-256:
  `9fd3dfa0e1c8589dc8552b7ba8929b977f9a750029d15d7dedd91a7f0b3c9732`.
- The dedicated Discord listener restarted as PID `75473`; the Jarvis gateway
  remained PID `56537` and was not restarted. The first post-deployment cron
  execution for the final controller, `436d01f301544a18bd079f7ffa79cd53`,
  completed `ok` at `2026-07-20T01:44:23+09:00`, advanced the poll cursor to
  `2026-07-20T01:43:58+09:00`, and left no room buffer. State and memory are
  version 2, the assistant remains enabled, and automatic sending is not
  paused. Automatic/approval/failure counters were unchanged, so deployment
  verification sent no KakaoTalk message.
- Branch/worktree: `main` at
  `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`.
- Completion mode: `review-required` because recurring intent routing, state,
  and memory behavior changed.

## Eighty-second KakaoTalk polling

- HIL status: completed in the originating Codex task; Discord thread id: none.
  The user explicitly requested changing the KakaoTalk polling interval from
  two minutes to one minute twenty seconds.
- Hermes Agent v0.18.2's installed `parse_schedule` accepts recurring interval
  durations only as integer minutes, hours, or days. It cannot represent
  `80s` or `1m20s`, and a standard cron expression cannot provide a reliable
  sub-minute offset. The exact interval is therefore implemented by the
  dedicated user launchd service
  `ai.hermes.jarvis-messenger-assistant-poll`, which keeps
  `--poll-loop --poll-interval-seconds 80` running.
- The existing Hermes cron job `643add69262e` was retained but paused after the
  launchd poller loaded successfully. This preserves a direct rollback path
  while preventing duplicate polling. The controller's existing file lock
  serializes the poller with the realtime Discord listener.
- The installer now creates and verifies the 80-second poller, then pauses a
  matching legacy Hermes cron. Dry-run output reports both actions. Its managed
  SOUL text and the controller's operational messages no longer describe the
  polling path as a two-minute cron. A first `StartInterval=80` implementation
  was rejected during production verification because launchd coalesced actual
  starts to about 120 seconds; the final persistent loop uses monotonic
  fixed-rate deadlines and skips only an overrun boundary.
- Local verification: all 58 tests passed, including the persistent 80-second
  launch-agent contract, fixed-deadline/overrun behavior, and legacy cron
  discovery. Both Python entry points compiled, installer help parsing passed,
  OKF validation passed, and `git diff --check` passed.
- Remote backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/cron/jobs.json.bak-poll-80s-20260720-014944`,
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-poll-80s-20260720-014944`,
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-poll-80s-20260720-014944`.
  The final fixed-rate controller was additionally backed up at
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-poll-fixed-80s-20260720-015500`,
  and the rejected launchd plist at
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-poll.plist.bak-messenger-assistant-20260720-015500`.
  A final transient-memory hardening deployment backed up the controller and
  memory at
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-transient-memory-20260720-020353`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/memory.json.bak-transient-memory-20260720-020353`.
  Deployed controller SHA-256:
  `d616c273156b5777d99147237dd394902252d6a5f8561384dc0e17d45fa1b75c`.
- The fixed-rate poller recorded consecutive Kakao polling boundaries at
  `2026-07-20T01:55:18+09:00` and
  `2026-07-20T01:56:38+09:00`, an exact 80-second difference. The poller logs
  initially remained empty. A later boundary failed closed on a Jarvis
  exact-one-tool-call mismatch without advancing the cursor; the persistent
  loop stayed alive and recovered on the following boundary.
- During that extended observation, a real new user message arrived asking
  whether a linked YouTube video had been watched. The enabled production
  workflow sent one automatic reply; this was not a test message. Its drafter
  also attempted to save the one-off question as relationship memory under
  `watch_request_from_user`. That transient entry was backed up and removed,
  and query/request/recent/status/weather key families are now rejected
  deterministically. Production memory is empty again.
- The final poller runs as PID `78360`. The assistant remains enabled,
  automatic sending is not paused, and no room buffer remains.
- The Discord listener remained PID `75473` and the Jarvis gateway remained
  PID `56537`; neither was restarted. Branch/worktree remains `main` at
  `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`.
- Completion mode: `review-required` because the recurring scheduler changed.

## Fresh-send verification boundary

- HIL status: completed in the Codex task; Discord thread id: none. The user
  reported an `assistant_status` automatic-send audit card for `이보빈` without
  a corresponding new visible KakaoTalk message and approved a controller fix.
- Production diagnosis reproduced the exact mismatch: the latest audit card
  was created at `2026-07-20T00:59:59+09:00`, while the latest identical
  KakaoTalk outgoing event was from `2026-07-20T00:24:33+09:00`, a 2,126-second
  gap. The relevant Jarvis sessions contained preview calls but no
  `send_message` call, proving that pre-send duplicate detection accepted the
  stale fixed response and skipped the actual send.
- Duplicate suppression and post-send read-back now require an exact text match
  whose outgoing timestamp is at or after the triggering boundary. Automatic
  replies use the latest incoming turn, approved or edited replies use the
  pending turn, and corrections use the audit-card creation time. A retry for
  the same trigger remains idempotent, while an older identical status response
  cannot satisfy a new request.
- The regression test failed before the fix with `send_calls=0` and passed
  afterward with one actual `dry_run=false` call. Two additional tests preserve
  same-trigger idempotency and verify that automatic sends use the latest
  incoming timestamp. All 48 controller tests, OKF validation, and
  `git diff --check` passed. No live KakaoTalk message was sent for testing.
- Remote controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-fresh-send-boundary-20260720-010708`.
  Deployed SHA-256:
  `32ea425347c07aff3c2cfc4cd3992103beae667502522aae47ef71d0135cd49f`.
- The dedicated Discord listener restarted as PID `71694`; the Jarvis gateway
  remained PID `56537` and was not restarted. The first post-deployment cron
  completed `ok` at `2026-07-20T01:10:44+09:00`, advanced the poll cursor to
  `2026-07-20T01:08:54+09:00`, and left no buffered room pending. The assistant
  remained enabled and automatic sending was not paused.
- Completion mode: `review-required` because recurring automatic-send
  verification behavior changed.

## Five-second buffer and no pre-send MCP dry-run

- HIL status: completed in the Codex task; Discord thread id: none. The
  approved scope changes the newest-message quiet period from 60 seconds to
  five seconds and removes the MCP `dry_run=true` step from every shared send
  path: automatic replies, approved or edited replies, and corrections.
- Each send still requires the final verified-direct-room policy guard, calls
  MCP `send_message` once with `dry_run=false`, and performs a read-back preview
  afterward. There is no second actual-send attempt. The two-minute polling
  schedule remains unchanged, so five seconds is not a polling SLA.
- Existing uncommitted work on `main` was preserved. No branch or worktree was
  created, matching the user's earlier explicit main-branch instruction.
- Local verification: 45 controller tests passed, including the four-second
  wait/five-second process boundary and a one-call `dry_run=false` send
  assertion. OKF validation and `git diff --check` passed. No live KakaoTalk
  message was sent for testing.
- Remote controller backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-buffer-5-no-dry-run-20260720-004628`.
  Deployed SHA-256:
  `1500d6134f1d50a88a33c756d3da922179ac852871080bc1a74d09fd9ae4af04`.
- The dedicated Discord listener restarted as PID `69533`; the Jarvis gateway
  remained PID `56537` and was not restarted. The first post-deployment cron
  completed `ok` at `2026-07-20T00:48:15+09:00`, advanced the poll cursor to
  `2026-07-20T00:47:51+09:00`, and left no buffered room pending. The assistant
  remained enabled and automatic sending was not paused.
- Completion mode: `review-required` because recurring automatic-send behavior
  was changed and pre-send validation was intentionally relaxed.

## All verified direct rooms and raised automatic-send limits

- HIL status: completed in the Codex task; Discord thread id: none. The
  approved scope enables every adapter-verified 1:1 room, raises the per-room
  automatic-send limit from 3 to 300 per 30 minutes, and raises the global
  limit from 10 to 100 per ten minutes.
- `allow_all_direct_chats=true` expands discovery beyond `allowed_chat_ids`,
  but buffering and final sends still require cached evidence that the exact
  `chat_id` came from `NTUser.directChatId`. Group and unverified rooms remain
  blocked before a KakaoTalk send call. Per-room exclusion and approval-only
  controls remain available.
- Existing uncommitted controller, test, task-note, and runbook changes on
  `main` were preserved. The user explicitly requested that this change also
  be made on `main`; no branch or worktree was created.
- Local verification: 44 controller tests passed, both Python entry points
  compiled, installer help parsing passed, OKF validation passed, and
  `git diff --check` passed. No live KakaoTalk message was sent for testing.
- Remote config is version 3 with `allow_all_direct_chats=true`. Backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-all-direct-rates-20260720-004001`
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json.bak-all-direct-rates-20260720-004001`.
- Deployed controller SHA-256:
  `34bdf275f4bba3ac14cf2ca4ed32a8f735451df1d44035800c0e67ae496f4e3d`.
  The dedicated Discord listener restarted as PID `68792`; the Jarvis gateway
  remained PID `56537` and was not restarted.
- The first post-deployment cron execution completed `ok` at
  `2026-07-20T00:42:18+09:00`. The assistant remained enabled, automatic
  sending was not paused, and the poll cursor advanced to
  `2026-07-20T00:41:50+09:00` with no buffered room left pending.
- Completion mode: `review-required` because the remote config and recurring
  automatic-send policy were changed.

## Automatic-reply threshold 0.70

- The primary model's reported confidence now permits automatic sending at
  `0.70` and above. Exactly `0.69` still creates an approval card.
- The classifier prompt, controller constant, boundary tests, and live runbook
  use the same threshold. Existing operational gates remain unchanged.
- All 42 controller tests, OKF validation, and `git diff --check` passed.
- The deployed controller SHA-256 is
  `bde7bfdce27c1793578c5e08865c5f23bf4d03ca05a35f4b0652bf0e9d82824f`;
  backup:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-confidence-070-20260720-002813`.
- The dedicated Discord listener reconnected as PID `67747`. Jarvis gateway
  PID `56537` was not restarted. The following two-minute cron completed `ok`
  at `2026-07-20T00:28:41+09:00` with no recorded error.
- Completion mode remains `review-required` because the recurring automatic
  send policy was relaxed.

## Bounded send-destination scan and failure diagnostics

- KakaoTalk MCP send resolution is bounded to the 20 most recent rooms through
  `kmsg chats --limit 20 --json`. This keeps the approval target search narrow
  without extending the existing timeout.
- The installed MCP distinguishes destination scan timeout, unresponsive UI,
  missing or ambiguous recent targets, and the actual send command. It returns
  `phase`, `scan_limit`, `elapsed_ms`, and `candidate_count` alongside its
  specific error code.
- The Jarvis controller now preserves those MCP diagnostics in Discord failure
  reports. It also accepts the source adapter's equivalent
  `failure_stage`/`failure_reason` fields, so neither adapter form is collapsed
  into a generic send failure.
- Deterministic tests cover the recent-20 command, destination-list timeout,
  target-not-found distinction, and controller rendering of both diagnostic
  shapes. All 137 KakaoTalk skill-repository tests and all 42 controller tests
  passed; OKF validation and `git diff --check` also passed.
- The local KakaoTalk skill checkout was fast-forwarded to `origin/main`
  `eca0008` (`Harden KakaoTalk send destination lookup`). Existing uncommitted
  image-send work was preserved and reconciled with the new bounded-scan code;
  the pre-sync stash remains as `pre-origin-main-sync-20260720-0023` for
  recovery.
- The remote MCP installation already contained the bounded scan and specific
  error codes, so it was neither overwritten nor restarted. Only the controller
  was deployed, with backup
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-kmsg-scan-diagnostics-20260720-001722`.
  A follow-up stage-classification deployment was backed up at
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-kmsg-stage-fix-20260720-002221`.
  Installed controller SHA-256:
  `90256b02cfedf78e31a4bba747b2736162706d51b82880443c9eee8c5871465b`.
- The dedicated Discord listener reconnected as PID `66914`; Jarvis gateway
  PID `56537` was not restarted. The controller `--check` passed with all
  checks true, including the KakaoTalk MCP and chat-ID allowlist.
- The first following two-minute cron completed `ok` at
  `2026-07-20T00:19:55+09:00`. A no-send MCP dry-run then validated the target
  through `phase=resolve_destination`, `scan_limit=20`, `candidate_count=20`,
  and `elapsed_ms=1730`; no KakaoTalk message was sent. After the final
  controller deployment, cron completed `ok` again at
  `2026-07-20T00:24:50+09:00` and remained scheduled every two minutes.
- Completion mode remains `review-required` because recurring controller and
  KakaoTalk send-routing behavior changed.

## Read-only MCP argument and retry hardening

- Incident session `20260719_234946_7c577d` called the expected
  `preview_messages` tool once for adapter chat ID `128426307555607`, but the
  Jarvis model replaced intentional empty `skill_dir` and `script_path` values
  with legacy local paths. The MCP read itself succeeded; the controller's
  exact-argument verifier correctly rejected the changed call before any send.
- The Jarvis tool prompt now puts the exact argument JSON before the call
  instruction and explicitly requires all keys, including empty strings, to be
  copied unchanged. It prohibits omitted/default-filled values, additional
  arguments, and inferred filesystem paths. Exact post-call verification is
  unchanged.
- A buffered-message exception no longer removes the room buffer in a
  `finally` block. The same entity IDs remain eligible for the next two-minute
  cron run, and only a successful processing path removes the buffer.
- The lost incident entity
  `kakaotalk_mac:128426307555607:3888414853475194881` was restored under the
  controller lock. An intermediate malformed multi-call attempt failed closed
  and left the buffer intact, demonstrating the retry path.
- The successful retry preview session `20260720_000612_d57418` called
  `preview_messages` exactly once with the expected target, chat ID,
  `skill_dir=""`, and `script_path=""`. Dry-run session
  `20260720_000625_0c10b1`, actual-send session
  `20260720_000703_30b7da`, and read-back session
  `20260720_000807_232f38` each used one exact MCP call. The restored weather
  question was recorded as processed, its buffer was removed, and one
  automatic weather reply was visibly verified.
- Local checks: Python compilation passed; all 38 unit tests passed, including
  prompt ordering/empty-value preservation and failure-retains-buffer followed
  by success-consumes-buffer; OKF validation and `git diff --check` passed.
- Installed controller SHA-256:
  `9656fd0a49790eec38a6f0265932bfdd6272ae0fc15c41a9c3430bfc0b7b04c3`.
  Backups:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-read-retry-20260720-000014`,
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/state.json.bak-read-retry-20260720-000014`,
  and
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-read-retry-v2-20260720-000600`.
- The dedicated Discord listener reconnected as PID `60443`; Jarvis gateway
  PID `56537` was not restarted. Cron execution
  `463728c4ac41446c9922df0a11a771d2` completed successfully and the two-minute
  schedule remains active.
- Completion mode remains `review-required` because recurring controller code
  was changed and deployed, and the recovered message produced an external
  KakaoTalk reply.

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
  `0.70` and above sends automatically, while lower or non-finite values create
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
- The original regression suite covered the `0.79`/`0.80`
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
