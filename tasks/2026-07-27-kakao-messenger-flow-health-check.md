---
type: Task
title: KakaoTalk messenger flow health check
status: done
date: 2026-07-27
---

# KakaoTalk messenger flow health check

## Lifecycle

- Task type: `incident-triage`
- HIL status: skipped; this was a direct read-only Codex request
- Branch/worktree: none; read-only operational checks
- Changed operational files: none
- Completion note:
  `tasks/2026-07-27-kakao-messenger-flow-health-check.md`
- Source ledger: none
- Completion mode: `done`

## Result

- The deterministic Jarvis messenger-controller path is healthy.
- The controller is currently stopped (`enabled=false`) as required by its
  fail-closed policy. Poll and Discord listener launchd services remain
  running, with no recorded last-poll or baseline error.
- A separate ad hoc Hermes Agent lookup issue is reproducible: a free-form
  prompt may invent an optional `chat_id`, causing a safe empty result. The
  same Agent request succeeds when instructed to omit `chat_id`.
- This Agent argument-selection issue does not affect the messenger controller,
  which constructs MCP arguments deterministically from the read-side room ID.
- No KakaoTalk message was sent.

## Checks

- `bin/hermes-remote check-ssh` — passed
- `bin/hermes-remote status` — default/Jarvis gateways and KakaoTalk MCP
  processes running
- `python3 -m unittest tests/test_messenger_assistant.py` — 117 passed
- `python3 scripts/hermes/validate_okf.py` — passed
- Source and installed messenger controller SHA-256 — identical
- Installed controller `--check` — every check true
- Source/installed KakaoTalk MCP adapter SHA-256 — identical
- MCP discovery — connected in 429 ms; 15 tools discovered
- Direct kmsg UI lookup — 3/3 passed in 15.27–15.90 seconds, one event each,
  with no timeout or stale `role='unknown'` selection signal
- Ad hoc Agent generic lookup — failed safely after supplying an invented
  `chat_id`
- Ad hoc Agent constrained lookup — passed with one
  `preview_messages` call and one event after omitting `chat_id`
- Deterministic controller preview — 3/3 passed in 0.75–0.76 seconds with ten
  context events per call
- No-send conversation binding — passed with `chat_id` strategy

## Follow-up

Harden the ad hoc Agent-facing preview contract so an optional `chat_id` is
accepted only when it was obtained from chat discovery, or retry target-only
resolution when a supplied `chat_id` produces an empty result. Add an
Agent-level regression check for the generic Korean lookup prompt before
changing the runtime.
