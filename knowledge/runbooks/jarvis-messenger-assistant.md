---
type: Runbook
title: Jarvis Messenger Assistant
description: Fail-closed KakaoTalk messenger assistant operated by the existing Jarvis profile through a private Discord control channel.
resource: repo://hermes-workspace/knowledge/runbooks/jarvis-messenger-assistant.md
tags: [hermes, jarvis, kakaotalk, discord, gateway, cron, human-in-the-loop]
timestamp: 2026-07-20T00:28:00+09:00
---

# Jarvis Messenger Assistant

## Purpose

The existing `jarvis` profile acts as a KakaoTalk messenger assistant. It reads
1:1 messages every two minutes while explicitly enabled, drafts replies with
`openai/gpt-5-nano`, and sends replies with a visible `[메신저 비서]` prefix
when the model reports confidence of at least `0.70`. Lower-confidence and
operationally unverifiable replies go to a private Discord approval channel.

This is a `remote-config` and recurring-automation change. Installation,
gateway restart, and future policy changes remain `review-required`.

## Architecture

- `scripts/hermes/messenger_assistant.py` is the deterministic controller and
  is installed into Jarvis' profile-specific `~/.hermes/profiles/jarvis/scripts/`
  directory.
- A Hermes script-only cron job wakes the controller every two minutes. The
  controller delegates each KakaoTalk read to a Jarvis one-shot restricted to
  the `openhuman-kakaotalk-mac` toolset. Jarvis directly calls the MCP tool and
  the controller consumes the verified tool result from that same Hermes
  session. The cron does not consume Discord commands.
- A user-level launchd service keeps `--discord-listen` connected to Discord
  Gateway and dispatches control-channel messages immediately. It catches up
  through the REST cursor after reconnecting, so a temporary disconnect does
  not lose commands.
- The controller reads the existing Jarvis Discord token at runtime. The token
  is never copied into controller config or the launchd plist.
- The private channel or private-thread fallback is added to
  `DISCORD_IGNORED_CHANNELS`, preventing the
  ordinary Jarvis conversational gateway from double-processing control replies.
- Every KakaoTalk operation goes through `JarvisKakaoAgent`: a Jarvis one-shot
  uses the Hermes-configured `openhuman-kakaotalk-mac` toolset and directly
  calls exactly one namespaced MCP tool. The controller verifies the primary
  model/provider, exact tool name, required arguments, one-call count, and raw
  tool result recorded in the same Jarvis session. It does not import the MCP
  SDK or adapter modules and does not invoke `kakaocli`, `kmsg`, or CuaDriver.
- The Jarvis execution prompt requires every supplied argument to remain exact,
  including intentional empty strings. In particular, it prohibits inferring
  or substituting local paths for `skill_dir` and `script_path`; the controller
  still rejects any recorded argument mutation instead of relaxing validation.
- Two-minute scans and previews use bounded result sizes so Hermes can retain
  the complete MCP tool result. A truncated or malformed session result fails
  closed instead of being reconstructed from model text.
- A Hermes one-shot call with tools disabled performs JSON classification and
  drafting. If the usage report does not show the configured primary nano
  model, automatic sending is prohibited. Its interface reports `intent`,
  `reply_kind`, `reply`, `summary`, `reason`, `confidence`, and
  `weather_location`; semantic risk flags are retained only for Discord audit.
- Linked pages are read with a separate Camofox identity named
  `hermes-messenger-isolated`. A failed isolated read is passed to the model as
  unavailable context instead of independently forcing approval.
- `OpenMeteoWeather` resolves an explicit model-extracted place through the
  Open-Meteo geocoding and forecast endpoints. Each public-data request is one
  verified Jarvis `terminal` call with an exact allowlisted HTTPS URL and
  read-only curl command; the controller consumes the raw recorded tool result.
- Durable state and extracted contact facts live under
  `~/.hermes/profiles/jarvis/messenger-assistant/` with user-only permissions.
  Raw KakaoTalk turns are not stored there.
- `allowed_chat_ids` is a required non-empty config list. Room discovery,
  buffering, classification, approval/correction handling, and actual sends all
  fail closed unless the adapter-provided `chat_id` is in that list.

## Control Commands

Only the single ID in `DISCORD_ALLOWED_USERS` is copied into the non-secret
assistant config and accepted by the controller.

- `메신저 시작`: set a new baseline and enable polling
- `메신저 종료`: block every KakaoTalk send and post a session report
- `메신저 상태`: show state, recent poll, pending approvals, and room controls
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
- A Jarvis gateway PID/start-time change disables the assistant. The identity
  reader accepts both the legacy plain PID file and Hermes 0.18.2's JSON PID
  record; an unparseable record is treated as invalid.
- Start creates a new baseline; messages received before it are summary-only.
- Stop blocks approvals and corrections as well as automatic replies.
- Only rooms whose adapter lookup reports the same `chat_id` from
  `NTUser.directChatId` are treated as 1:1 rooms; `member_count` is not used.
- Only configured `allowed_chat_ids` are considered before direct-room lookup.
  Messages in every other room are ignored even when `is_from_me=true`, and a
  final send guard prevents stale approval or audit cards from reaching them.
- Direct-room evidence is obtained through the MCP `find_chat` tool and cached
  only when the same `chat_id` includes the adapter source
  `NTUser.directChatId`. A preview-followup guard produces no new evidence and
  therefore fails closed for an uncached room.
- A new incoming message or user-authored outgoing message invalidates an
  outstanding draft for the same room. Messages beginning with the visible
  `[메신저 비서]` prefix are never candidates, preventing reply loops.
- Consecutive messages are buffered until 60 seconds after the newest message.
- A buffered-message processing exception retains that room buffer. The next
  two-minute cron run retries the same entity IDs, and the buffer is removed
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
  `어느 지역 날씨를 알려줄까?`; the next turn is joined through the same
  room's recent context without persisting raw clarification state.
- `assistant_status` replies are replaced with the fixed friendly text
  `응, 지금 정상적으로 작동 중이야 🙂`; internal process, gateway, MCP,
  Discord, model, and polling information is never exposed in KakaoTalk.
- Per-room automatic sends are capped at three per 30 minutes. Global automatic
  sends are capped at ten per ten minutes.
- Sends first ask Jarvis to call MCP `send_message(dry_run=true)` for the
  adapter-provided direct-room destination. After validation, Jarvis calls the
  same MCP tool once with `dry_run=false`, and the controller asks Jarvis for
  an MCP preview to verify the visible message. There is no CuaDriver fallback
  and no second actual-send attempt. An adapter timeout or uncertain read-back
  is reported with its specific reason while the approval remains pending.
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
interactive login, `메신저 시작` rechecks MCP read access. Send readiness and
the resolved destination are checked through MCP dry-runs immediately before
each send.

Device approval, OTP, and other second-factor steps are never collected by
Jarvis. A failed MCP poll does not advance the message cursor and is reported
to Discord; the next scheduled poll retries through the same MCP path.
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
  --allowed-chat-id <adapter-chat-id> --dry-run'

ssh bobeen '/Users/bobeenlee/.hermes/hermes-agent/venv/bin/python \
  /tmp/install_messenger_assistant.py \
  --controller /tmp/messenger_assistant.py \
  --allowed-chat-id <adapter-chat-id>'
```

On later upgrades, omitting `--allowed-chat-id` preserves the non-empty list
from the installed config. A first install or an existing config without the
list requires the flag. The installer backs up the previous config before
writing the new one.

The installer:

1. creates or reuses a private `메신저-비서` Discord channel, falling back to a
   private thread under the configured home channel when the bot lacks
   server-level channel-management permission;
2. backs up Jarvis `.env` and `SOUL.md` with a timestamp;
3. installs the controller and non-secret config (for a named profile, the cron
   `--script` value is the filename relative to
   `~/.hermes/profiles/jarvis/scripts`);
4. adds the control channel to `DISCORD_IGNORED_CHANNELS`;
5. creates the disabled-state file and a two-minute Kakao-only script cron;
6. installs and starts the user launchd service
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
ssh bobeen '/bin/launchctl print gui/$(id -u)/ai.hermes.jarvis-messenger-assistant-discord'
bin/hermes-remote status
```

Before live use, confirm in the private Discord channel:

1. `메신저 상태` receives a response without waiting for the two-minute cron
   and reports `종료`.
2. A gateway restart still leaves it `종료`.
3. `메신저 시작` establishes a new baseline.
4. `오늘 날씨 어때?` automatically asks for a region; replying `서울` produces
   a validated current-weather answer.
5. `너의 상태는 어때?` produces only the friendly fixed status text.
6. Confidence `0.70` sends automatically, while `0.69`, fallback-model use,
   ambiguous weather, and MCP send uncertainty produce approval or failure
   audit according to their operational path.
7. A message in a different direct room, including a user-authored
   `is_from_me=true` message, creates no buffer or approval card; a direct send
   attempt to its `chat_id` is rejected before the KakaoTalk MCP call.
8. A forced read-only preview argument mismatch leaves the room buffer present;
   a subsequent successful run consumes it exactly once.
9. A forced destination scan failure reports `phase=resolve_destination` and
   `scan_limit=20`; a recent-target miss is distinguishable from a scan timeout
   and from an actual `kmsg send` failure.

For controller-only updates, back up and replace the installed script, then
restart only `ai.hermes.jarvis-messenger-assistant-discord`. The script-only
cron loads the new file on its next two-minute run; the Jarvis gateway does not
need a restart unless profile configuration, environment, or tool registration
also changed.

## Rollback

Keep the assistant stopped, boot out the realtime launchd service, pause or
remove its cron job, restore the timestamped Jarvis `.env` and `SOUL.md`
backups, and restart only the Jarvis gateway. Do not delete or reset the `kmsg`
encrypted credential cache unless the user explicitly asks; that is a separate
credential action.
