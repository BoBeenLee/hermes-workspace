---
type: Task
title: Stabilize kmsg KakaoTalk search result activation
status: review-required
date: 2026-07-27
---

# Stabilize kmsg KakaoTalk search result activation

## Lifecycle

- Task type: `ops-change`
- HIL status: skipped; the request was made directly in Codex
- Completion mode: `review-required`
- Source repository: `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-skill`
- Implementation branch/worktree:
  - `codex/verified-direct-send-fallback-20260726`
  - `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-skill/.worktrees/verified-direct-send-fallback-20260726`
- Main commits:
  - `e10bb80` (`fix(kmsg): stabilize KakaoTalk search activation`)
  - `e4e0fc1` (`fix(mcp): normalize omitted preview arguments`)
  - `e7ba735` (`fix(mcp): sync Hermes KakaoTalk runtime`)
  - `0caa2cf` (`chore(deploy): enforce Hermes MCP source sync`)
- Remote target: `bobeen`

## Cause

- Search scans retained AX element handles and click coordinates while KakaoTalk
  was still replacing the result rows.
- An exact text score could outweigh the penalty for an invalidated element whose
  live role had become `unknown`.
- Expanded scans included focused, main, and application roots, allowing offscreen
  rows and unrelated windows to become candidates.
- When the chat list was absent, an unvalidated `mainWindow` could be used as the
  search root.

## Changes

- Restrict search candidates to visible `AXRow` and `AXCell` elements inside a
  validated chat-list window.
- Reject candidates outside the list window or overlapping the search field.
- Require the candidate frame to remain stable across consecutive scans and
  refresh it immediately before clicking.
- Use a 12-second resolution deadline and a cross-process KakaoTalk UI lock.
- Recover a missing list with `Cmd+2`; if soft recovery fails, close all KakaoTalk
  windows and perform one hard-reset retry.
- Normalize zero, empty, and nonexistent absolute `kakaocli_bin` values emitted
  for omitted MCP preview arguments so Hermes falls back to configured defaults.
- Add Swift behavioral tests for candidate eligibility, frame stability, and the
  UI lock, plus source-level integration contracts and an MCP sentinel regression
  test.
- Add `scripts/sync-hermes-mcp-runtime.sh` with read-only drift checking by
  default and explicit, syntax-validated, backed-up, atomic deployment.
- Make the existing remote kmsg deployment verification fail before other
  checks unless the repository adapter and installed Hermes adapter have the
  same SHA-256 hash.
- Parse the default and Jarvis Hermes YAML configs so multiline `KMSG_BIN`
  values and the configured skill directory are validated against the actual
  runtime rather than an obsolete hard-coded path.

## Verification

- Red loop before the fix:
  - `kmsg read "이보빈" --limit 1 --verified-friend-fallback --trace-ax`
  - selected `role='unknown'` at a stale coordinate and timed out at 20 seconds.
- Swift tests: 5 passed.
- Vendored kmsg Python tests: 33 passed.
- KakaoTalk MCP tests: 160 passed.
- Release build: passed.
- Remote canary:
  - list-only state: 3/3 passed in 8-15 seconds;
  - list plus detached chat window: passed in 17 seconds;
  - detached window with list initially absent: soft recovery and read passed in
    17 seconds;
  - no KakaoTalk send was attempted.
- Installed main-build smoke: passed in 15 seconds and auto-closed only the
  transient target chat.
- Hermes Agent end-to-end preview:
  - called only `kakaotalk_mac.preview_messages`;
  - model supplied `chat_id=0` and a nonexistent `/usr/local/bin/kakaocli`;
  - server normalized both and returned `ok=true`, `event_count=1`,
    `resolved_by=visible_chats`;
  - no send tool was called and no message content was included in the
    verification response.
- Final KakaoTalk state: one `KakaoTalk` list window; no test read process.

## Remote deployment

- Installed paths:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/vendor/kmsg/.build/release/kmsg`
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor/kmsg/.build/release/kmsg`
- Final SHA-256:
  `4d8220715b2ba2015035661307461716a8cb2cfb1012ad63bdccc4955c6f5223`
- Original-binary backups:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/vendor/kmsg/.build/release/kmsg.bak-search-stability-20260727-011835`
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor/kmsg/.build/release/kmsg.bak-search-stability-20260727-011835`
- Pre-main-build backups:
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/vendor/kmsg/.build/release/kmsg.bak-pre-main-build-20260727-012059`
  - `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor/kmsg/.build/release/kmsg.bak-pre-main-build-20260727-012059`
- Hermes MCP adapter:
  - installed path:
    `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py`
  - SHA-256:
    `1cb3e6d1db6dd6aefb02c5cdd70c1cf4d4707d17218822bb12c63900d304ef4b`
  - backup:
    `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-sentinel-normalization-20260727-013258`
  - pre-sync backup:
    `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/server/adapters/kakaotalk/mcp_server.py.bak-source-sync-20260727-014749`
  - source and remote installed files have identical SHA-256 values.
  - default and `jarvis` gateways restarted successfully after deployment.
- Recurrence-prevention verification:
  - default local `check` is read-only and detects drift;
  - local deploy tests confirm syntax validation, timestamped backup, exact
    replacement, and no write on invalid Python;
  - `scripts/sync-hermes-mcp-runtime.sh check bobeen` passed with adapter
    SHA-256
    `1cb3e6d1db6dd6aefb02c5cdd70c1cf4d4707d17218822bb12c63900d304ef4b`;
  - `scripts/verify-remote-kmsg-deploy.sh bobeen` passed with 15 MCP tools and
    the configured runtime kmsg executable.

## Source ledger

None; this task used repository code, automated tests, and direct remote
diagnostics.

## Follow-up: bounded pre-open search-miss retry

### Lifecycle

- Task type: `ops-change`
- HIL status: `skipped`; the user directly approved the recommended retry
  change in Codex
- Implementation branch:
  `codex/kmsg-search-miss-retry-20260727`
- Implementation worktree:
  `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-skill/.worktrees/kmsg-search-miss-retry-20260727`
- Source commit:
  `3c31cfd` (`fix(kmsg): retry pre-open search misses once`)
- Changed files:
  - `vendor/kmsg/Sources/kmsg/KakaoTalk/ChatSearchRetryPolicy.swift`
  - `vendor/kmsg/Sources/kmsg/KakaoTalk/ChatWindowResolver.swift`
  - `vendor/kmsg/SwiftTests/ChatSearchRetryPolicyTests.swift`
  - `vendor/kmsg/tests/test_send_command_contract.py`
- Completion mode: `review-required`

### Cause and change

- The initial chat lookup, recovered chat lookup, and exact friend lookup
  shared one 12-second deadline. When the earlier stages consumed that budget,
  the final friend search could observe zero AX rows before KakaoTalk finished
  refreshing them.
- Only a final pre-open `SEARCH_MISS` now triggers one retry.
- Before that retry, kmsg presses Escape, clears the search-field AX cache,
  returns to the Chats tab, and then re-enters the Friends tab.
- The retry receives a fresh 12-second deadline.
- Focus failures, input failures, result-open failures, and failures after a
  candidate click are not retried, preserving duplicate-send protection.

### Verification and deployment

- Red regression loop initially failed because `ChatSearchRetryPolicy` did not
  exist.
- Swift tests: 7 passed.
- Vendored kmsg Python tests: 34 passed.
- Release build and `git diff --check`: passed.
- Branch pushed to
  `origin/codex/kmsg-search-miss-retry-20260727`.
- Configured remote runtime binary SHA-256:
  `0e079ba55652e9b7fc3262ccdf1ad7638a3fe4b32528261b19a4c6dc08cea446`.
- Remote backup:
  `/Users/bobeenlee/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor/kmsg/.build/release/kmsg.bak-search-miss-retry-20260727-1556`.
- `scripts/verify-remote-kmsg-deploy.sh bobeen` passed with 15 MCP tools.
- Remote `kmsg status --verbose` confirmed Accessibility granted,
  authentication ready, and KakaoTalk running.
- No gateway restart was needed because each send launches the configured
  binary as a new process.
- No live KakaoTalk message was sent during verification.
- Source ledger: none; the task used repository code, automated tests, and
  direct remote diagnostics.
