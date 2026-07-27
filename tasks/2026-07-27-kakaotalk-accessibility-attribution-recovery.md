---
type: Task
title: Recover Jarvis KakaoTalk binding from Accessibility attribution failure
status: review-required
date: 2026-07-27
---

# Recover Jarvis KakaoTalk binding from Accessibility attribution failure

## Lifecycle

- Task type: `incident-triage`
- HIL status: `skipped`; the request and permission approval were made directly
  in Codex
- Branch: `main`
- Worktree:
  `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Changed operational files: none; temporary remote config edits were restored
- Source ledger: none
- Completion mode: `review-required` because the user granted macOS
  Accessibility permission

## Incident

Jarvis retained one KakaoTalk reply buffer but repeatedly failed before sending:

```text
kmsg_ui_unresponsive
stage=resolve_destination
scan_limit=20
candidate_count=0
```

The controller failed closed, attempted no KakaoTalk send, and retried the same
buffer on later polling cycles.

## Cause

macOS TCC attributed the launchd poller's `kmsg` Accessibility request to the
responsible Hermes Python runtime rather than to the `kmsg` executable.
The generated Python runtime path did not have Accessibility permission, so
each automatic binding attempt opened an Accessibility authorization warning
and System Settings. Those foreground windows prevented KakaoTalk from
providing a usable chat list.

Direct SSH probes succeeded because they ran under a different responsible
process context. Unified TCC logs confirmed the automatic poller PID and
generated Python path as the responsible process.

## Recovery

- The user granted Accessibility permission to the exact Hermes Python runtime
  shown by macOS.
- TCC subsequently returned `authValue=2` for `kmsg` calls attributed to the
  poller.
- The authorization warning and System Settings windows were closed.
- KakaoTalk was restored to the Chats tab.
- A proposed localhost self-SSH `kmsg` wrapper was smoke-tested but not
  activated. Both Hermes configs were restored to the original pinned `kmsg`
  path, and the temporary wrapper was removed.
- Timestamped pre-change backups were retained:
  - `/Users/bobeenlee/.hermes/config.yaml.bak-kmsg-self-ssh-20260727-140951`
  - `/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.bak-kmsg-self-ssh-20260727-140951`

## Verification

- `bin/hermes-remote check-ssh` — passed
- `bin/hermes-remote status` — gateway, Jarvis, CuaDriver, and poller running
- Installed controller `--check` — every check true
- CuaDriver Accessibility and Screen Recording — granted
- Post-permission TCC decision for the poller-attributed `kmsg` call —
  `authValue=2`
- No-send conversation binding — `ok=true`, `candidate_count=20`, binding v2
- Original buffered turn — removed after successful reprocessing
- Discord — processing and approval cards created; no new binding-failure card
- KakaoTalk UI — one KakaoTalk window on the Chats tab; authorization and
  System Settings windows absent
- Actual KakaoTalk send during recovery — none

The recovered turn remains in one Discord approval card because the existing
automatic-reply confidence policy evaluated it at `0.00`. That is a safe policy
outcome rather than a transport failure.
