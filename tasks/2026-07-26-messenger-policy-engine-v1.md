# Messenger policy engine v1

- Task type: `ops-change` and `remote-config`
- HIL status: `skipped` — direct Codex request, not a Discord-gated request
- Branch: `main`
- Worktree:
  `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Base: `origin/main` at `5bfa43f` after `git pull --ff-only origin main`
- Completion mode: `review-required`
- Source ledger: `none`

## Applied behavior

- `메신저 시작` retains the default ordinary-room policy: only unread
  incoming messages received within five minutes are candidates.
- `메신저 시작: <자연어 조건>` compiles policy schema v1 once, then stores
  exact included/excluded room names, a bounded lookback, read state,
  mandatory unanswered state, and an optional semantic condition.
- The controller evaluates room, lookback, read state, and unanswered state
  deterministically. Only residual content, intent, or current-time criteria
  cross the per-turn model seam.
- The policy interface is versioned and fail-closed. It accepts at most 20
  included and excluded rooms combined, a lookback up to 24 hours, and
  500-character normalized or semantic conditions. Invalid model types,
  unsupported requirements, fallback models, and confidence below `0.80`
  prevent startup.
- A lookback uses a bounded first scan and preview of up to 50 messages per
  chat. Later operator or `[메신저 비서]` outgoing messages make earlier
  incoming messages answered.
- Policy mismatches are scoped to the active session, create no reply or
  approval card, and are reported to Discord without message text.
- The configured 이보빈 static exception bypasses session filtering and read
  state, but does not inherit a policy lookback before the current start time.
  Existing direct-room verification, duplicate suppression, reply-confidence,
  and rate controls remain active.
- Discord help and status text document the structured policy and distinguish
  it from the default unread/five-minute behavior.

## Changed files

- `scripts/hermes/messenger_assistant.py`
- `scripts/hermes/install_messenger_assistant.py`
- `tests/test_messenger_assistant.py`
- `knowledge/runbooks/jarvis-messenger-assistant.md`
- `tasks/2026-07-26-messenger-policy-engine-v1.md`

## Remote backups

- Controller:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-policy-v1-20260726-210411`
- Config:
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json.bak-messenger-assistant-20260726-210629`
- Poller plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-poll.plist.bak-messenger-assistant-20260726-210629`
- Discord listener plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-discord.plist.bak-messenger-assistant-20260726-210629`
- Jarvis environment:
  `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak-messenger-assistant-20260726-210629`
- Jarvis SOUL:
  `/Users/bobeenlee/.hermes/profiles/jarvis/SOUL.md.bak-messenger-assistant-20260726-210629`

## Verification

- `python3 -m py_compile ...` — passed
- `python3 -m unittest tests/test_messenger_assistant.py -v` — 99 passed
- `python3 scripts/hermes/validate_okf.py` — passed
- `git diff --check` — passed
- Installer dry-run — preserved all-direct scope, 30-second polling, and the
  이보빈 read-state exception
- Live read-only compiler smoke:
  - input:
    `1시간 전부터 답하지 않은 메시지 김서현님 채팅방만 자동 응답 진행`
  - exact room: `김서현`
  - lookback: `3600` seconds
  - read state: `unread`
  - reply state: `unanswered`
  - semantic condition: empty
  - compile confidence: `0.95`
- Installed controller `--check` — all checks true
- Local and installed controller SHA-256 — identical
- State migration — version 4, assistant remained enabled, no active session
  condition, polling and automatic replies remained unpaused
- Poller and Discord listener — loaded and running
- Latest Kakao poll — successful, no current poll error
- No real KakaoTalk test message was sent.
