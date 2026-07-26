# Messenger session conditions and Discord help

- Task type: `ops-change` and `remote-config`
- HIL status: `skipped` — direct Codex request, not a Discord-gated request
- Branch: `main`
- Worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Completion mode: `review-required`
- Source ledger: `none`

## Applied behavior

- `메신저 시작` uses the default unread-first policy for ordinary rooms.
- `메신저 시작: <자연어 조건>` compiles one session condition with the
  primary nano model before enabling the assistant.
- Conditions are limited to 500 characters, reject secret-like text, and
  require compilation confidence of at least `0.80`.
- A non-exempt room requires a primary-model per-turn match at confidence
  `0.80` or higher before intent routing and reply drafting.
- Condition mismatches create no reply or approval card. They are marked
  processed and reported without message text in one poll-level grouped audit.
- A technical matcher failure retains the buffer for retry.
- The configured 이보빈 read-state exception bypasses the session matcher but
  retains every existing reply-confidence and final-send guard.
- Explicit stop and gateway-identity shutdown clear the session condition.
- `도움말` and `메신저 도움말` return the same grouped Discord command
  reference without internal IDs, paths, secrets, or raw configuration.

## Changed files

- `scripts/hermes/messenger_assistant.py`
- `scripts/hermes/install_messenger_assistant.py`
- `tests/test_messenger_assistant.py`
- `knowledge/runbooks/jarvis-messenger-assistant.md`
- `tasks/2026-07-26-messenger-session-conditions-help.md`

## Remote backups

- Pre-feature controller:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-session-conditions-20260726-204742`
- Pre-calibration controller:
  `/Users/bobeenlee/.hermes/profiles/jarvis/scripts/messenger_assistant.py.bak-condition-calibration-20260726-205213`
- Config:
  `/Users/bobeenlee/.hermes/profiles/jarvis/messenger-assistant/config.json.bak-messenger-assistant-20260726-204758`
- Poller plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-poll.plist.bak-messenger-assistant-20260726-204758`
- Discord listener plist:
  `/Users/bobeenlee/Library/LaunchAgents/ai.hermes.jarvis-messenger-assistant-discord.plist.bak-messenger-assistant-20260726-204758`
- Jarvis environment:
  `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak-messenger-assistant-20260726-204758`
- Jarvis SOUL:
  `/Users/bobeenlee/.hermes/profiles/jarvis/SOUL.md.bak-messenger-assistant-20260726-204758`

## Verification

- `python3 -m py_compile ...` — passed
- `python3 -m unittest tests/test_messenger_assistant.py -v` — 93 passed
- `python3 scripts/hermes/validate_okf.py` — passed
- `git diff --check` — passed
- Installer dry-run — preserved all-direct scope and 이보빈 read-state exception
- Installed controller `--check` — all checks true
- State migration — version 3 with empty session condition and audit batch
- Assistant state — remained enabled, no current poll error
- Poller and Discord listener — running
- Local and installed controller SHA-256 — identical
- Live synthetic condition smoke:
  - input: `가족 방에서 질문일 때만`
  - normalized: `가족 방에서 수신된 메시지 중 질문인 경우에만 자동 응답`
  - compile confidence: `0.95`
  - synthetic family-room question: matched
- `bin/hermes-remote status` — gateway and Jarvis profile running
- No real KakaoTalk test message was sent.

## Prompt calibration incident

The first live smoke returned confidence `0.72` because the compiler copied the
controller-owned five-minute age guard into an invented absolute time window.
The prompt contract now keeps controller guards out of the user condition and
defines confidence bands for rules that are or are not evaluable from the
available local fields. The same live smoke then compiled at `0.95` and matched
the synthetic turn.
