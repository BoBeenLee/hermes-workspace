# hermes mac 프로필 정리: 5개 → default + jarvis

- Task type: `remote-config` (profile delete, launchd gateway uninstall, SOUL/cron edit)
- HIL status: 사용자 직접 승인 (`남길 것: default + jarvis 둘로 진행`)
- Target: `bobeenlee@bobeen` (`BoBeenui-MacBookPro-2.local`), Hermes Agent v0.20.6
- Branch/worktree: `none` for remote operations
- Completion mode: `review-required`

## Requested Outcome

실사용 데이터에 맞춰 프로필을 `default` + `jarvis` 둘로 줄이고, jarvis에 남은
Bot Mode 이전 잔재(v1 라우팅 규칙, 정지된 cron job, 백업 파일)를 정리한다.

## Pre-state

| 프로필 | 모델 | 세션 | 마지막 사용 | 활성 cron | channel_directory |
| --- | --- | --- | --- | --- | --- |
| default | Qwen3.8-27B-MLX | 5 | 2026-06-08 | 0 | - |
| jarvis | Qwen3.8-27B-MLX | 3 | 2026-08-29 | 0 (1건 paused) | 12.9KB / 48 targets |
| content | gpt-oss-120b | 1 | 2026-07-10 | 0 | 648B / 3 targets |
| product | gpt-oss-120b | 1 | 2026-07-10 | 0 | 758B / 3 targets |
| preflight | Qwen3.8-27B-MLX | 0 | 2026-06-20 | 0 | 67B / 0 platforms |

`content`/`product`는 SOUL.md만 다르고 모델·스킬(25개)이 동일했다. `preflight`는
채팅 세션이 0건이었다.

## Remote Changes

1. gateway 정지: `hermes -p <p> gateway stop` (content, product, preflight).
   라이브 unix socket 때문에 정지 전에는 `profile export`가 `[Errno 102]
   Operation not supported on socket`으로 실패한다.
2. 아카이브: `hermes profile export` → `/Users/bobeenlee/hermes-archive-20260829/`
   - `content.tar.gz` 18M (996 entries), `product.tar.gz` 26M (1177),
     `preflight.tar.gz` 21M (987). 전부 SOUL.md + config.yaml 포함 확인.
   - `jarvis-SOUL.md.pre-cleanup`, `jarvis-jobs.json.pre-cleanup`.
   - 복구는 `hermes profile import <tar.gz>`.
3. launchd gateway 서비스 3개 uninstall → plist 제거.
4. `hermes profile delete <p> -y` 3건. wrapper(`~/.local/bin/<p>`)도 함께 제거됐다.
5. jarvis `SOUL.md`: `## Team` 섹션과 v1 라우팅 규칙 4줄 삭제, Bot Mode 네이티브
   위임(`@<bot>` 멘션, `message_agent()`, 3-round 캡)으로 교체. Ops Log의
   `owner: jarvis|product|content` → `owner: jarvis|<bot>`.
   `<!-- messenger-assistant:managed -->` 블록은 그대로 보존했다.
6. jarvis `cron/jobs.json`: `jarvis-messenger-assistant` (every 2m, 2026-07-20부터
   paused) 제거. 실제 폴링은 launchd `ai.hermes.jarvis-messenger-assistant-poll`이
   담당하므로 중복이었다. jobs 1 → 0.
7. jarvis 백업 파일 29개 삭제 (`SOUL.md.bak-*` 12, `config.yaml*bak*` 17).

## 회귀와 복구: kanban dispatcher

`preflight` 삭제 후 kanban dispatcher가 끊겼다.

- dispatcher는 config가 아니라 런타임 lock 파일
  `~/.hermes/kanban/.dispatcher.lock` (2026-06-20 생성, 0 bytes)로 결정된다.
  게이트웨이 중 lock을 잡은 하나만 dispatch한다.
- 삭제 전 로그에서 `default`와 `jarvis` 둘 다
  `another gateway already holds the dispatcher lock; this gateway will NOT
  dispatch` 상태였다. lock 보유자가 `preflight`였고, 삭제로 사라졌다.
- 게이트웨이는 재시작 없이 lock을 다시 잡지 않는다. `hermes gateway restart`
  (default)로 복구했다: `holding singleton dispatcher lock` →
  `kanban dispatcher: embedded in gateway (interval=60.0s)`.
- kanban 보드가 전 상태 0건이라 밀린 작업은 없었다.

**교훈**: 프로필 삭제 전 `config.yaml`의 `kanban:` 블록만 보면 안 된다. 그 블록은
비어 있어도 dispatcher는 동작한다. 판단 근거는 게이트웨이 로그의
`kanban dispatcher:` 라인과 lock 파일이다.

## Verification

- `hermes profile list` → `default`, `jarvis` 2개, 둘 다 `running`
- `hermes gateway status` → default PID 4429 supervised, jarvis PID 2714
- `launchctl list | grep hermes` → gateway 2개(`gateway`, `gateway-jarvis`),
  `jarvis-messenger-assistant-poll/-discord`, `camofox`, `mlx-qwen`, `mac-manager`.
  삭제한 3개 gateway 서비스 없음.
- `hermes -p jarvis cron list` → `No scheduled jobs`
- `hermes kanban stats` → 전 status 0건, dispatcher 재가동
- jarvis SOUL.md 3938 bytes, managed 블록 마커 2개 보존

## jarvis config migration v33 → v39

2026-08-29 업데이트 세션 기록은 `hermes config migrate`를 5개 프로필에 적용했다고
적었지만 jarvis는 반영되지 않았다(`doctor` → `Config version outdated (v33 → v39)`).
default만 v39였다. 이번에 적용했다.

- 백업: `config.yaml.bak-cfgmigrate-v33v39-20260829-171303` (18134 bytes) +
  아카이브 사본 `hermes-archive-20260829/jarvis-config.yaml.pre-migrate-v33`.
- 텍스트 diff는 대부분 YAML 재포맷이다. 파싱 후 semantic diff로 실제 변경은 3건:

  | 키 | v33 | v39 |
  | --- | --- | --- |
  | `_config_version` | 33 | 39 |
  | `delegation.max_iterations` | 50 | 250 |
  | `display.background_process_notifications` | `all` | `concise` |

  제거/추가된 키는 0건. 두 동작 변경 모두 upstream 기본값 상향이고, 워크스페이스
  문서 어디에도 이 키를 의도적으로 튜닝한 기록이 없어 그대로 수용했다.
- default의 v37 → v39는 버전 필드 한 줄뿐이었지만 jarvis는 실제 동작 키가 바뀌므로
  게이트웨이를 재시작했다. jarvis PID 2714 → 4757, Discord home-channel startup
  notification 발송, `Channel directory built: 48 target(s)` 재확인.
  재시작 후 jarvis는 dispatcher lock을 default에 양보한다(정상).
- 검증: `hermes -p jarvis doctor` → `✓ Config version up to date (v39)`,
  `✓ No deprecated config keys or env vars`.
- `platform 'cli'/'discord' references unknown toolset` 경고 4건은
  `knowledge/runbooks/platform-toolsets-validation-warning.md`에 기록된 알려진
  false positive다. 조치 없음.

## jarvis 역할 재정의

프로필을 줄인 뒤에도 jarvis는 자기소개에서 여전히 "AI PM 어시스턴트로, 요청하신
작업을 정리하고 실행하거나 위임해서 결과를 보고"한다고 답했다. 위임할 워커가
없는데 위임을 전제한 정체성이 남아 있었다.

출처는 두 곳뿐이었다. 프로필에 `USER.md` / `AGENTS.md` / `MEMORY.md`는 없고
(`~/.hermes` 최상위에도 없다), 워크스페이스 문서에도 이 프레이밍은 없다.

- `SOUL.md`
  - `chief AI PM for a Discord-based AI workspace` →
    `operator agent on this Mac, reachable through Discord and the CLI`
  - Mission의 `execute or delegate` → `do the work yourself`
  - Bot Mode 위임 규칙 2줄(`@<bot>` 멘션, `message_agent()`, 3-round 캡) 삭제.
    티메이트 프로필이 0개라 죽은 규칙이었다. 두 번째 봇을 만들 때 되살린다.
  - 추가: `You are the only agent profile on this host. There is no worker to
    delegate to: do the work, or say plainly why you cannot.` 와
    `Do not describe yourself as a PM who routes or hands off work.`
  - Ops Log Format의 `owner: jarvis|<bot>` 줄 삭제. 프로필이 하나라 항상 jarvis다.
  - `<!-- messenger-assistant:managed -->` 블록은 보존(마커 2개 확인).
- `profile.yaml` description (kanban orchestrator가 읽는다)
  - `Chief AI PM that coordinates product service development and content production.` →
    `Operator agent on this Mac: Discord and CLI interface, desktop control via
    computer_use/cua-driver, and the KakaoTalk messenger assistant.`
  - `hermes profile describe jarvis --text ...`

백업: `hermes-archive-20260829/jarvis-SOUL.md.pre-role-change`.
`SOUL.md`는 매 메시지마다 새로 읽히므로 게이트웨이 재시작은 불필요하다.

검증:

- `SOUL.md` 3939 chars, managed 블록 마커 2개 잔존
- `hermes profile describe jarvis` → 새 description 반환
- 라이브 자기소개 확인은 로컬 MLX Qwen3.8-27B의 한국어 생성이 250초 타임아웃을
  넘겨 이번에는 응답을 받지 못했다. 파일 수준 변경만 확인된 상태다.

## Follow-up (미실행)

- `knowledge/runbooks/hermes-workflow-optimization.md`,
  `platform-toolsets-validation-warning.md`, `hallmark-product-skill.md`는
  삭제된 프로필을 계속 언급한다. 과거 작업 기록이라 그대로 뒀다.
  현재 상태 문서인 `knowledge/tools/local-llm-providers.md`만 갱신했다.
- jarvis Discord `Slash command sync timed out` 경고는 업데이트 세션에서 이미
  관찰된 것으로, 이번 변경과 무관하다.
