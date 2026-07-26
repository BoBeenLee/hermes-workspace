# KakaoTalk read-state exception for 이보빈

- Task type: `remote-config` and `ops-change`
- HIL status: `skipped` — direct Codex request, not a Discord-gated request
- Branch: `main`
- Worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Completion mode: `review-required`
- Source ledger: `none`

## Applied behavior

- Verified `이보빈` as adapter-confirmed human direct chat
  `128426307555607` using `NTUser.directChatId`.
- Added `read_state_exempt_chat_ids` and configured only that chat ID.
- New incoming messages in that room may enter the automatic-reply buffer
  regardless of current KakaoTalk read state.
- The active scan boundary, five-minute age limit, incoming-direction check,
  direct-room verification, operator-reply cancellation, duplicate
  suppression, model confidence gate, and rate limits remain unchanged.
- No historical read-message backfill was performed.
- The assistant remained enabled; polling and automatic replies remained
  unpaused. The room is neither excluded nor approval-only.

## Changed files

- `scripts/hermes/messenger_assistant.py`
- `scripts/hermes/install_messenger_assistant.py`
- `tests/test_messenger_assistant.py`
- `knowledge/runbooks/jarvis-messenger-assistant.md`
- `tasks/2026-07-26-kakao-read-state-exempt-ibobin.md`

## Remote backups

- Controller:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-read-state-exempt-20260726-202444`
- Config:
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json.bak-messenger-assistant-20260726-202636`
- Poller plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-poll.plist.bak-messenger-assistant-20260726-202636`
- Discord listener plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-discord.plist.bak-messenger-assistant-20260726-202636`
- Jarvis environment:
  `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak-messenger-assistant-20260726-202636`
- Jarvis SOUL:
  `/Users/bobeenlee/.hermes/profiles/jarvis/SOUL.md.bak-messenger-assistant-20260726-202636`

## Verification

- `python3 -m unittest tests/test_messenger_assistant.py -v` — 79 passed
- `python3 scripts/hermes/validate_okf.py` — passed
- `git diff --check` — passed
- Installed controller `--check` — all checks true
- Local and installed controller SHA-256 — identical
- Remote config version — 4
- Remote `read_state_exempt_chat_ids` —
  `["128426307555607"]`
- Poller launchd state — running, never exited
- Discord listener launchd state — running, never exited
- Latest Kakao poll — successful, no current poll error
- `bin/hermes-remote status` — gateway and Jarvis profile running

## Deployment incident

The first install attempt hit transient launchd exit 5 while bootstrapping the
poller immediately after bootout. The plist, permissions, and executable paths
were valid, and a later bootstrap succeeded. The installer now retries this
specific bootstrap seam up to five times with bounded backoff. A regression
test covers the first-attempt failure followed by successful reload.
