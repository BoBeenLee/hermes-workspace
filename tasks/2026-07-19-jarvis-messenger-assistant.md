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
  entry, managed `SOUL.md` section, controller/config/state files, three-minute
  Kakao-only script cron, realtime Discord launchd listener, Jarvis gateway
  restart
- Secret handling: existing Discord token is read only on the remote host;
  KakaoTalk login values are entered directly by the user through `kmsg`; no
  secret is handled by Jarvis or committed
- Completion mode: `review-required`

## Checks

- Private Discord control surface: private thread `메신저-비서`
- Cron job: `643add69262e`, active, `every 3m`, script-only/no-agent
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
  - persisted controller state — `enabled: false`, zero pending approvals
- Human review/action still required:
  - enter the KakaoTalk ID and changed password in the interactive `kmsg`
    prompts already opened on the remote Mac
  - complete any KakaoTalk device/OTP approval manually
  - issue `메신저 상태` and then `메신저 시작` in the private Discord thread
- Source ledger: Context7 `/discord/discord-api-docs` for Discord Gateway
  MESSAGE_CREATE, heartbeat/resume, and message-content intent requirements;
  Context7 Hermes docs plus installed v0.18.2 CLI help for cron syntax
- Completion mode: `review-required`
