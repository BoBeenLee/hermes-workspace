# hermes mac Hermes Agent 업데이트 v0.20.2 → v0.20.6

- Task type: `remote-config` (git checkout, venv, launchd plist, cua-driver)
- HIL status: `n/a` (직접 요청, 백업 정책만 사전 승인)
- Target: `bobeenlee@bobeen` (`BoBeenui-MacBookPro-2.local`)
- Branch/worktree: `none` for remote operations
- Completion mode: `review-required`

## Requested Outcome

원격 Mac의 Hermes Agent를 최신 upstream으로 올린다.

## Pre-state

- `Hermes Agent v0.20.2 (2026.8.16)` · upstream `f8f43c95`
- install method `git`, checkout `~/.hermes/hermes-agent`, branch `main`
- `git rev-list --left-right --count HEAD...@{u}` → `0 2879` (2879 commits behind)
- 로컬 변경 없음 (clean), 디스크 579Gi free
- `updates.pre_update_backup: false`

`hermes version`은 "Up to date"로 잘못 보고했다. 실제 격차는 `hermes update --check`와
checkout의 `git rev-list`로만 드러났다. 버전 판단을 `hermes version` 문자열에 의존하지 말 것.

## Remote Changes

- `hermes update --backup --yes`
  - 전체 pre-update 백업(state 스냅샷 + `HERMES_HOME` zip) 강제. config의
    `pre_update_backup: false`를 이 실행에 한해 덮어썼다.
  - checkout `f8f43c95` → `aff5125f` (2026-08-23), venv 의존성 재설치, Web UI 재빌드,
    model catalog 캐시 갱신.
  - bundled skill 4개 갱신(`hermes-agent`, `computer-use`, `teams-meeting-pipeline`,
    `google-workspace`) 후 `content`/`jarvis`/`preflight`/`product` 프로필에 전파.
  - `cua-driver 0.20.0 → 0.22.2`.
- gateway auto-restart 실패:
  `cannot import name 'line_input' from 'hermes_cli.cli_output'`.
  구 gateway 프로세스가 갱신된 checkout에 대해 구 `sys.modules`를 물고 있어서 발생.
  업데이터가 안내한 대로 수동 복구했다.
- gateway 수동 재시작 5개 프로필: default, product, content, jarvis, preflight.
- 재시작 후 launchd plist 5개가 `stale relative to the current Hermes install`로 떴다.
  프로필별 `hermes gateway start`로 service definition 재생성.

## Verification

- `hermes --version` → `Hermes Agent v0.20.6 (2026.8.27) · upstream aff5125f`
- `hermes gateway status` → `Service definition matches the current Hermes install`,
  5개 프로필 전부 supervised (default/content/jarvis/preflight/product)
- `launchctl list | grep hermes` → gateway 5개 전부 last exit status `0`
- `bin/hermes-remote verify-computer-use` → cua-driver 0.22.2로 window 목록 정상 반환
- smoke test: `hermes -z "Reply with exactly: OK"` → `OK`

## Follow-up (승인 후 실행)

### config migration v37 → v39

- 백업: `config.yaml.bak-cfgmigrate-v37v39-20260829-164803` (main + content/jarvis/preflight/product 프로필 5개).
- `hermes config migrate` 실행.
- 실제 diff는 `_config_version: 37` → `39` 한 줄뿐. 구조 변경 없음.
- 검증: `hermes doctor` → `✓ Config version up to date (v39)`, 잔여 이슈 0건.
- 경고 3건(`platform 'cli'/'discord' references unknown toolset 'antigravity-worker'`,
  `'openhuman-kakaotalk'`)은 `knowledge/runbooks/platform-toolsets-validation-warning.md`에
  기록된 알려진 false positive. 조치 없음.
- config 변경이 버전 필드뿐이라 gateway 재시작은 생략했다.

### 잔여 서비스 재시작

`launchctl kickstart -k gui/$UID/<label>`:

- `ai.hermes.jarvis-messenger-assistant-poll` → PID 3585
- `ai.hermes.jarvis-messenger-assistant-discord` → PID 3587
- `ai.hermes.camofox` → PID 3589
- `ai.hermes.mlx-qwen` → PID 3617, `/v1/models`가 5초 내 `Qwen3.8-27B-MLX-4bit` 응답

launchd `last exit status = -15`는 kickstart의 SIGTERM이며 정상이다.
`poller.error.log`는 재시작 후 새 기록 없음(최종 2026-08-02).

재시작하지 않은 것과 이유:

- `mlx-qwen`은 homebrew `/opt/homebrew/bin/mlx_lm.server`로 뜬다. hermes venv와 무관해서
  이번 업데이트로 재시작할 이유는 없었다. 요청에 따라 재시작만 했다.
- `application.ai.hermes.mac-manager.*`는 LaunchAgent plist가 없다. 사용자가 띄운
  네이티브 GUI 앱(`HermesMacManager.app`)이라 `launchctl kickstart` 대상이 아니고,
  hermes venv도 쓰지 않는다. 재시작하려면 앱을 직접 종료 후 다시 실행해야 한다.

## Messaging / Bot 상태 (업데이트 후)

- `content`, `jarvis`, `product`: `Gateway running with 1 platform(s)` — Discord bot 정상.
  channel directory는 jarvis 48 targets, content/product 각 3 targets.
- `default`: `DISCORD_BOT_TOKEN` 없음 → `No messaging platforms enabled`. 원래 상태다.
- `preflight`: 0 platforms. cron 실행과 kanban dispatcher singleton lock 담당.
- 경고: 3개 프로필 모두 시작 10분 뒤
  `[Discord] Slash command sync timed out — Discord rate-limit bucket may be saturated;
  will retry on next reconnect`. 멘션/메시지 경로는 살아 있고 slash command 등록만
  지연된 상태. 다음 reconnect에 재시도한다.

## 신규 CLI 기능 (v0.20.6)

- `hermes peer` — 다른 Hermes gateway를 peer로 등록하고 `peer dm <peer>[/<agent>]`로
  원격 agent의 Bot Chat에 메시지를 넣고 응답을 받는다. 상대가 `api_server` platform을
  띄우고 있어야 하며 `API_SERVER_KEY`는 로컬 `~/.hermes/.env`에 저장된다. 미설정.
- `hermes browser close-profile` — real-profile 브라우징용. 브라우저 프로세스 트리를
  죽이므로 파괴적.
- `hermes worktree list|prune` — `hermes -w` 세션이 쌓은 `.worktrees/` 정리.

## CLI Surface Change

`hermes version` 서브커맨드가 제거됐다. v0.20.6의 서브커맨드 목록에 `version`이 없고
`worktree`, `browser`, `peer`가 추가됐다. 버전 확인은 `hermes --version`을 쓴다.
`bin/hermes-remote`나 스크립트에서 `hermes version`을 호출하는 곳이 있으면 수정 필요.
