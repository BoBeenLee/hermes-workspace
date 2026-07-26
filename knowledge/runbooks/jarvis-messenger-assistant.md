---
type: Runbook
title: Jarvis Messenger Assistant
description: Fail-closed KakaoTalk messenger assistant operated by the existing Jarvis profile through a private Discord control channel.
resource: repo://hermes-workspace/knowledge/runbooks/jarvis-messenger-assistant.md
tags: [hermes, jarvis, kakaotalk, discord, gateway, cron, human-in-the-loop]
timestamp: 2026-07-26T17:15:00+09:00
---

# Jarvis Messenger Assistant

## Purpose

The existing `jarvis` profile acts as a KakaoTalk messenger assistant. It reads
1:1 messages every 30 seconds while explicitly enabled, drafts replies with
`openai/gpt-5-nano`, and sends replies with a visible `[메신저 비서]` prefix
when the model reports confidence of at least `0.70`. Lower-confidence and
operationally unverifiable replies go to a private Discord approval channel.

This is a `remote-config` and recurring-automation change. Installation,
gateway restart, and future policy changes remain `review-required`.

## Architecture

- `scripts/hermes/messenger_assistant.py` is the deterministic controller and
  is installed into Jarvis' profile-specific `~/.hermes/profiles/jarvis/scripts/`
  directory.
- A user-level launchd service named
  `ai.hermes.jarvis-messenger-assistant-poll` keeps the controller's
  `--poll-loop --poll-interval-seconds 30` process alive. The loop uses a
  dynamic monotonic fixed-rate deadline, so normal request duration does not
  extend the next start interval and an overrun skips only already-missed
  boundaries. It reloads durable pause, immediate-run, and interval controls
  while waiting. The poller does not consume Discord commands.
- Hermes 0.18.2 accepts only integer-minute recurring intervals, so its legacy
  `every 2m` job is retained in paused state for rollback rather than used as
  an imprecise seconds-based scheduler. The controller lock prevents the realtime
  listener and poller from executing state mutations concurrently.
- A user-level launchd service keeps `--discord-listen` connected to Discord
  Gateway and dispatches control-channel messages immediately. It catches up
  through the REST cursor after reconnecting, so a temporary disconnect does
  not lose commands. If a Kakao scan currently holds the controller lock, the
  listener waits and reloads the latest durable state before applying the
  command rather than dropping the Discord event.
- The controller reads the existing Jarvis Discord token at runtime. The token
  is never copied into controller config or the launchd plist.
- The private channel or private-thread fallback is added to
  `DISCORD_IGNORED_CHANNELS`, preventing the
  ordinary Jarvis conversational gateway from double-processing control replies.
- Every KakaoTalk operation goes through the `KakaoMcpAdapter` interface. Its
  implementation loads the existing profile MCP server definition, starts the
  stdio server with the MCP Python SDK, initializes one client session, calls
  exactly one `kakaotalk_mac.*` tool with controller-owned arguments, normalizes
  structured output, and closes the subprocess. The controller never invokes
  `kakaocli`, `kmsg`, or CuaDriver directly.
- Jarvis models are no longer part of KakaoTalk tool selection, argument
  construction, or MCP result transport. They remain responsible for intent
  routing, drafting, typed-memory extraction, and allowlisted public-data
  lookup only.
- Polling scans and previews use bounded result sizes. A malformed structured
  MCP result fails closed, and a 180-second adapter deadline terminates the
  SDK-managed stdio call.
- `ConversationPolicy` separates intent routing from reply drafting. The intent
  router receives only the current `new_turn` and the room's explicit dialogue
  state; recent context and long-term memory cannot influence its decision.
  `weather` is accepted only when the router selects it and the current turn
  explicitly asks about weather, or an unexpired weather-location state exists.
- The reply drafter runs only after `other` is locked as the intent. It may use
  recent context and typed contact memory to phrase the answer, but it cannot
  change the locked intent. A weather reply generated for a non-weather turn is
  held for approval instead of being sent automatically.
- Explicit dialogue state is stored separately in state schema v2. A weather
  request with no location creates `pending_intent=weather_location` for 15
  minutes. Resolution, another completed intent, or expiry clears that state.
- `메신저 시작: <자연어 조건>` compiles one session-only automatic-reply
  condition with the primary nano model before the assistant is enabled. The
  compiler records the trusted raw condition, normalized condition, whether
  ordinary rooms may include already-read new messages, confidence, and
  compilation time. Invalid, fallback-model, secret-like, overlong, or
  confidence-below-`0.80` conditions leave the assistant stopped.
- A non-exempt room with an active session condition receives a context-free
  condition decision before intent routing. It sees only the trusted
  condition, current KST time, room name, current incoming turn, and read state
  captured at scan time. A match requires the primary nano model and
  confidence of at least `0.80`; KakaoTalk text cannot change the condition.
- Condition mismatches create no reply or approval card. They are marked
  processed and reported without message text in one room/reason/count summary
  per polling cycle. A technical condition-call failure retains the room
  buffer for retry.
- Long-term memory schema v2 permits only typed `profile`, `preference`,
  `relationship`, and `constraint` facts. Every fact must cite entity IDs from
  the current turn. Untyped legacy entries, weather locations, recent queries,
  and workflow state are removed rather than exposed to the intent router.
  Transient key families such as `query`, `request`, `recent`, `status`, and
  `weather` are rejected deterministically even if the model assigns an
  otherwise allowed memory type.
- Hermes one-shot calls run with tools disabled. If the usage report does not
  show the configured primary nano model, automatic sending is prohibited.
  Semantic risk flags are retained only for Discord audit.
- Linked pages are read with a separate Camofox identity named
  `hermes-messenger-isolated`. A failed isolated read is passed to the model as
  unavailable context instead of independently forcing approval. Only links
  supplied by the other party in the current turn are opened; operator-sent
  links remain text context without redundant browser calls.
- `OpenMeteoWeather` resolves an explicit model-extracted place through the
  Open-Meteo geocoding and forecast endpoints. Each public-data request is one
  verified Jarvis `terminal` call with an exact allowlisted HTTPS URL and
  read-only curl command; the controller consumes the raw recorded tool result.
- Durable state and extracted contact facts live under
  `~/.hermes/profiles/jarvis/messenger-assistant/` with user-only permissions.
  Raw KakaoTalk turns are not stored there.
- `allow_all_direct_chats=true` permits every room whose adapter lookup proves
  the same `chat_id` through `NTUser.directChatId`. Group rooms and rooms that
  lack this exact evidence remain blocked at discovery and at the final send
  guard. Deployments that leave this setting false continue to use the
  `allowed_chat_ids` allowlist.
- `read_state_exempt_chat_ids` is an explicit per-room exception to the
  unread-only trigger rule. For those IDs, new incoming messages after the
  active scan boundary may enter the reply buffer even if KakaoTalk already
  reports them as read. The five-minute age limit, incoming-direction check,
  duplicate suppression, direct-room verification, operator-reply
  cancellation, confidence gate, and rate limits still apply.
- `self_authored_reply_chat_ids` is a narrower opt-in subset of
  `read_state_exempt_chat_ids`. In those explicitly named direct rooms, a new
  manually authored outgoing message may also enter the reply buffer. Messages
  beginning with `[메신저 비서]` remain ineligible, so an assistant response
  cannot trigger another assistant response. A self-authored trigger cannot
  create or update counterparty memory. Other rooms keep the incoming-only
  rule.

## Control Commands

Only the single ID in `DISCORD_ALLOWED_USERS` is copied into the non-secret
assistant config and accepted by the controller.

- `메신저 시작`: clear any old session condition, set a new baseline, and
  enable the default unread-first policy
- `메신저 시작: <자연어 조건>`: compile and confirm a session-only condition,
  then set a policy-derived scan boundary and enable polling. For example,
  `메신저 시작: 최근 1시간 동안 김서현님 방의 답하지 않은 메시지만`
- `메신저 종료`: block every KakaoTalk send and post a session report
- `메신저 상태`: show state, recent poll, pending approvals, and room controls
- `도움말` / `메신저 도움말`: show the same grouped command reference for
  conditions, polling, approvals, room controls, and memory
- `폴링 주기`: show the current interval
- `폴링 주기 45초` / `폴링 주기 2분`: change the live polling interval
  between 5 seconds and 60 minutes
- `폴링 상태`: show pause state, interval, latest attempt/success/error, and
  the unread-only five-minute automatic-reply window
- `폴링 즉시실행`: request one poll without waiting for the next deadline
- `폴링 일시정지`: stop new KakaoTalk scans without stopping the assistant
- `폴링 재개`: resume and request one immediate poll before normal scheduling
- `인증 완료`: verify user-completed Kakao read/send login without retrying or
  handling any authentication value
- `자동답변 재개`: clear a global automatic-send rate pause

Reply to an approval card with:

- `승인`
- `수정: <message>`
- `보류`
- `상세`

Reply to an automatic-send audit card with `정정: <message>`.

Reply to an approval or audit card with:

- `방 제외` / `방 포함`
- `방 자동답변 끄기` / `방 자동답변 켜기`
- `기억 보기`
- `기억 추가: 항목=내용`
- `기억 수정: 항목=내용`
- `기억 삭제: 항목`
- `기억 전체삭제` followed by the generated confirmation command

## Fail-Closed Rules

- Initial state is disabled.
- Session conditions are limited to 500 characters and rejected when they look
  like credentials or secrets. Compilation occurs before the new baseline, so
  a rejected condition cannot partially start the assistant.
- Session conditions are cleared by explicit stop and gateway-identity
  automatic shutdown. Changing a condition requires stop followed by another
  start command.
- A Jarvis gateway PID/start-time change disables the assistant. The identity
  reader accepts both the legacy plain PID file and Hermes 0.18.2's JSON PID
  record; an unparseable record is treated as invalid.
- Start creates a new baseline; messages received before it are summary-only.
- Start invalidates pending or held approval cards whose latest message is
  older than the new baseline, or whose timestamp is missing or malformed,
  without restoring their entity IDs to the automatic-reply buffer.
- Stop blocks approvals and corrections as well as automatic replies.
- Only rooms whose adapter lookup reports the same `chat_id` from
  `NTUser.directChatId` and classifies the associated `NTUser` as `human` are
  treated as 1:1 rooms; `member_count` is not used. Non-zero `userType`,
  business/public-institution verification, AlimTalk, bot, BizChat, or an
  explicitly non-writable channel marks the destination as non-human and
  excludes it before drafting or sending.
- With `allow_all_direct_chats=true`, every discovered room may enter the
  direct-room lookup, but no room may be buffered or sent to until the adapter
  proves that exact `chat_id` as `NTUser.directChatId`. A final send guard
  prevents stale approval or audit cards from reaching unverified or group
  rooms. With the setting false, the original `allowed_chat_ids` scope applies.
- Direct-room evidence is obtained through the MCP `find_chat` tool and cached
  only when the same `chat_id` includes the adapter source
  `NTUser.directChatId` and `direct_chat_kind=human`. The cache records a direct
  policy version, so legacy direct-only evidence is rejected until refreshed.
  A preview-followup guard produces no new evidence and therefore fails closed
  for an uncached or stale-policy room.
- Only a current unread message from the other party can enter the reply
  buffer by default. A user-authored outgoing message is context only,
  invalidates an outstanding draft, and cancels buffered incoming messages at
  or before its timestamp because the operator has already responded. The
  sole exception is an adapter-verified direct room explicitly listed in
  `self_authored_reply_chat_ids`; there, the new manual outgoing message
  becomes the replacement reply trigger after the older work is cancelled.
  Messages beginning with the visible `[메신저 비서]` prefix remain context
  and do not trigger either cancellation or another reply.
- Consecutive messages are buffered until five seconds after the newest
  message. Because KakaoTalk polling uses the configured interval, this is a
  post-message quiet-period gate rather than a five-second polling SLA.
- Each incremental scan requests unread metadata. Messages absent from the
  current unread set are never automatic-reply candidates, even when they
  appear in the incremental history, unless their room ID is explicitly listed
  in `read_state_exempt_chat_ids`. In an exempt room, only new incoming
  messages from the incremental scan are considered; the controller does not
  backfill older read history. Candidate messages older than the active
  start/scan boundary or more than five minutes old are not automatically
  answered; stale items are marked processed and reported to Discord without
  copying their message text.
- Session policy schema v1 extracts exact included/excluded room names, a
  bounded lookback of up to 24 hours, `unread|any` read state, mandatory
  `unanswered` reply state, and an optional semantic condition. Room, lookback,
  read state, and unanswered state are evaluated deterministically. Only the
  remaining content, intent, or current-time rule uses the per-turn model.
- A lookback policy moves only the first ordinary-room scan boundary and raises
  the bounded per-chat history/preview limit to 50. An incoming message is
  already answered when a later operator or `[메신저 비서]` outgoing message
  exists. Nonmatching fingerprints are scoped to the active session so a
  later policy may reconsider them.
- An active policy may expand ordinary-room collection to read messages only
  when its compiled `read_state` is `any`. Static
  `read_state_exempt_chat_ids` take precedence over session conditions: those
  rooms bypass condition matching and unread filtering, but never inherit a
  session lookback before the current start time. All direct-room,
  reply-confidence, duplicate, and rate controls remain active.
- `recent_context` preserves both sides of the conversation. Every event has
  `speaker_role=operator|other_party`, `speaker_name`, and a `speaker_key`.
  Counterparties use `speaker_key=other_party:<name>`, so multiple participants
  in group-derived context remain distinct even though automatic sends still
  require a separately verified 1:1 room. The upstream adapter currently
  exposes sender names but not stable sender IDs.
- The start summary reuses unread metadata from the first successful
  incremental scan instead of launching a second seven-day MCP scan. A summary
  delivery failure is recorded and retried from a later successful result, so
  it cannot prevent new-message polling or cursor persistence.
- A successful incremental scan persists its cursor and room buffers before
  classification, drafting, link lookup, or sending begins. Later processing
  latency therefore cannot make the same scan appear unsuccessful.
- A buffered-message processing exception retains that room buffer. The next
  configured poll retries the same entity IDs, and the buffer is removed
  only after processing succeeds. The Discord failure notice states that the
  retry remains scheduled.
- Unknown/fallback model use, confidence below `0.70`, an empty reply, weather
  lookup failure, or an ambiguous weather location requires approval.
- Money/contracts, schedule changes, business commitments, medical/legal or
  emergency content, credentials, links, attachments, responsibility or
  relationship decisions, harmful style, and remembered facts do not
  independently block automatic sending. The model flags them in the Discord
  audit card, and the selected policy uses model confidence as the sole content
  gate.
- Missing required details produce a short automatic clarification at
  confidence `0.70` or above. A weather question without a location sends
  `어느 지역 날씨를 알려줄까?` and creates a typed, 15-minute explicit
  dialogue state. Only a router-confirmed follow-up during that window can
  complete the weather request; recent context and contact memory cannot open
  or prolong the state.
- A model-selected weather intent without an explicit current weather request
  or valid pending location state fails closed before Open-Meteo is called. It
  becomes a Discord approval card with a grounding reason and cannot be sent
  automatically.
- `assistant_status` replies are replaced with the fixed friendly text
  `응, 지금 정상적으로 작동 중이야 🙂`; internal process, gateway, MCP,
  Discord, model, and polling information is never exposed in KakaoTalk.
- Per-room automatic sends are capped at 300 per 30 minutes. Global automatic
  sends are capped at 100 per ten minutes.
- Sends call MCP `send_message` exactly once with `dry_run=false` for the
  adapter-verified direct-room `chat_id`; there is no pre-send MCP dry-run.
  The controller then asks Jarvis for an MCP preview to verify the visible
  message. There is no CuaDriver fallback and no second actual-send attempt.
  An adapter timeout or uncertain read-back is reported with its specific
  reason while the approval remains pending.
- State schema v4 stores the versioned policy and session-scoped skipped
  fingerprints in addition to `condition_audit_batch` and the
  `condition_skipped` statistic. Existing string-style session conditions are
  migrated to policy v1 with their normalized text as a semantic rule.
- Duplicate suppression and post-send read-back require both exact message
  text and an outgoing timestamp at or after the triggering boundary. The
  boundary is the latest incoming turn for automatic replies, the pending
  turn for approved or edited replies, and the audit-card creation time for
  corrections. An older identical fixed response cannot satisfy a newer send.
- The KakaoTalk MCP resolves a send destination from only the 20 most recent
  rooms with `kmsg chats --limit 20 --json`. Do not increase the timeout as the
  first response to a send failure. Use the returned `error`, `phase`,
  `scan_limit`, `elapsed_ms`, and `candidate_count` to distinguish destination
  scan timeout, unresponsive UI, missing/ambiguous recent target, actual send
  failure, and read-back mismatch. The controller includes these diagnostics
  in its Discord failure report.
- Explicit-location current-weather questions and approved weather edits use
  Open-Meteo geocoding followed by a forecast lookup. Multiple plausible
  populated locations, mismatched coordinates, out-of-range fields, altered
  terminal calls, non-primary models, or observations older than 30 minutes
  fail closed. Validated values are formatted deterministically and then sent
  through KakaoTalk MCP.
- KakaoTalk read state is never changed intentionally.

## KakaoTalk Recovery

Jarvis never reads, stores, or types the Kakao account, password, OTP, or
device-approval value. The user performs the initial `kmsg` login in an
interactive terminal on the remote Mac and enters all authentication values
directly:

```bash
/opt/homebrew/bin/kmsg auth login
```

`kmsg` owns its encrypted credential cache. The controller checks read auth
only through MCP `auth_status`; it does not launch KakaoTalk or invoke a login
command itself. If login is unavailable, it fails closed, disables the
assistant, and requests manual action in Discord. After the user completes the
interactive login, `메신저 시작` rechecks MCP read access. Each send uses the
adapter-verified direct-room `chat_id` in its single actual MCP call and is
checked afterward through the read-back preview; there is no pre-send readiness
dry-run.

Device approval, OTP, and other second-factor steps are never collected by
Jarvis. A failed direct MCP poll does not advance the message cursor and is
reported to Discord; the next scheduled poll retries through the same adapter.
Likewise, a failure after polling but before buffered classification or reply
completion retains the buffer so advancing the scan cursor cannot lose the
message.

## Installation

Run from the control workspace after the HIL approval summary is accepted:

```bash
bin/hermes-remote check-ssh
bin/hermes-remote status

scp scripts/hermes/messenger_assistant.py \
  scripts/hermes/install_messenger_assistant.py \
  bobeen:/tmp/

ssh bobeen '/Users/bobeenlee/.hermes/hermes-agent/venv/bin/python \
  /tmp/install_messenger_assistant.py \
  --controller /tmp/messenger_assistant.py \
  --allow-all-direct-chats \
  --read-state-exempt-chat-id 128426307555607 \
  --self-authored-reply-chat-id 128426307555607 \
  --dry-run'

ssh bobeen '/Users/bobeenlee/.hermes/hermes-agent/venv/bin/python \
  /tmp/install_messenger_assistant.py \
  --controller /tmp/messenger_assistant.py \
  --allow-all-direct-chats \
  --read-state-exempt-chat-id 128426307555607 \
  --self-authored-reply-chat-id 128426307555607'
```

On later upgrades, omitting `--allow-all-direct-chats` preserves an enabled
value from the installed config. A deployment may instead keep the setting
false and pass one or more `--allowed-chat-id` values. The installer backs up
the previous config before writing the new one.

The installer:

1. creates or reuses a private `메신저-비서` Discord channel, falling back to a
   private thread under the configured home channel when the bot lacks
   server-level channel-management permission;
2. backs up Jarvis `.env` and `SOUL.md` with a timestamp;
3. installs the controller and non-secret config;
4. adds the control channel to `DISCORD_IGNORED_CHANNELS`;
5. creates the disabled-state file, installs the configurable Kakao-only
   launchd poller with a 30-second default, and pauses the legacy Hermes cron
   if it exists;
6. installs and starts the separate user launchd service
   `ai.hermes.jarvis-messenger-assistant-discord` for realtime Discord commands.

Restart the Jarvis gateway only after inspecting the installer result:

```bash
ssh bobeen '/Users/bobeenlee/.local/bin/hermes --profile jarvis gateway restart'
```

## Verification

```bash
python3 -m unittest tests/test_messenger_assistant.py -v
python3 scripts/hermes/validate_okf.py

ssh bobeen '/Users/bobeenlee/.hermes/hermes-agent/venv/bin/python \
  /Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py \
  --config /Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json \
  --check'

ssh bobeen '/Users/bobeenlee/.local/bin/hermes --profile jarvis cron list --all'
ssh bobeen '/Users/bobeenlee/.local/bin/hermes --profile jarvis cron status'
ssh bobeen '/bin/launchctl print gui/$(id -u)/ai.hermes.jarvis-messenger-assistant-poll'
ssh bobeen '/bin/launchctl print gui/$(id -u)/ai.hermes.jarvis-messenger-assistant-discord'
bin/hermes-remote status
```

Before live use, confirm in the private Discord channel:

1. `메신저 상태` receives a response without waiting for the Kakao poller
   and reports `종료`.
2. A gateway restart still leaves it `종료`.
3. `메신저 시작` establishes a new baseline.
4. `오늘 날씨 어때?` automatically asks for a region; replying `서울` produces
   a validated current-weather answer.
5. `너의 상태는 어때?` produces only the friendly fixed status text.
6. Confidence `0.70` sends automatically, while `0.69`, fallback-model use,
   ambiguous weather, and MCP send uncertainty produce approval or failure
   audit according to their operational path.
7. A fresh unread message from the other party in a newly discovered
   adapter-verified direct room is buffered. A read message, a manual
   `is_from_me=true` message, a message older than five minutes, a group room,
   or a final send without cached `NTUser.directChatId` evidence is rejected
   before the KakaoTalk send MCP call. For a room listed in
   `read_state_exempt_chat_ids`, a fresh incoming incremental message is
   buffered even when absent from the unread set; the same message in any
   other room remains excluded.
8. A mixed preview labels operator messages separately and assigns different
   `speaker_key` values to each named counterparty.
9. A forced read-only preview argument mismatch leaves the room buffer present;
   a subsequent successful run consumes it exactly once.
10. A forced destination scan failure reports `phase=resolve_destination` and
   `scan_limit=20`; a recent-target miss is distinguishable from a scan timeout
   and from an actual `kmsg send` failure.
11. Repeating an `assistant_status` request after an older identical fixed
    response still performs one new actual send; retrying the same trigger
    recognizes an outgoing match after that trigger and does not resend.
12. `도움말` and `메신저 도움말` return identical grouped help without IDs,
    paths, secrets, or raw configuration values.
13. `메신저 시작: 최근 1시간 동안 김서현님 방의 답하지 않은 메시지만`
    compiles to policy v1 with exact room `김서현`, 3600-second lookback,
    `read_state=unread`, `reply_state=unanswered`, and no semantic matcher.
    Unsupported, over-24-hour, malformed, fallback-model, and low-confidence
    conditions leave the assistant stopped.
14. A non-exempt policy mismatch creates no send or approval card, is recorded
    only for the current session, and appears in the poll-level metadata
    summary. A semantic-condition call exception retains the buffer.
15. A policy lookback never backfills a static read-state exception room before
    the current start time.
16. The configured 이보빈 static exception bypasses the session matcher but
    still passes reply confidence, direct-room, duplicate, and rate guards.
17. A new manual outgoing message in the configured 이보빈 self-authored-reply
    room enters the normal intent and reply pipeline. The same message in any
    other room stays context-only, and a `[메신저 비서]` outgoing message never
    enters the reply buffer.

For controller-only updates, back up and replace the installed script, then
restart `ai.hermes.jarvis-messenger-assistant-poll` and
`ai.hermes.jarvis-messenger-assistant-discord`. The Jarvis gateway does not
need a restart unless profile configuration, environment, or tool registration
also changed.

## Rollback

Keep the assistant stopped, boot out both messenger-assistant launchd services,
resume the paused legacy cron only when rolling back to the old scheduler,
restore the timestamped Jarvis `.env` and `SOUL.md` backups, and restart only
the Jarvis gateway. Do not delete or reset the `kmsg`
encrypted credential cache unless the user explicitly asks; that is a separate
credential action.
