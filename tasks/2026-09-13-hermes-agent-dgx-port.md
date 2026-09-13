# DGX Spark 를 두 번째 Hermes 호스트로 올리고 신원을 dgx-jarvis / mac-jarvis 로 가른다

- Task type: `host-bootstrap` (원격 두 대의 상태를 바꿨다)
- HIL status: 사용자 직접 요청 (`DGX 에도 hermes 엔진 이식 진행`), 범위·신원 배치는 사전 합의
- Target: `bobeenlee@100.103.30.62` (DGX Spark, 쓰기), `bobeen` (hermes Mac, 쓰기)
- Branch/worktree: `.worktrees/hermes-dgx-port-20260913`
- Completion mode: `review-required`

## Requested Outcome

hermes Mac 의 구성을 DGX 에 두 번째 호스트로 올린다. 범위는 에이전트 코어이며,
카카오톡 데몬 이식은 companion 슬롯이 하나뿐이라 다음 세션으로 미룬다.
선행 세션([PR #5](https://github.com/BoBeenLee/hermes-workspace/pull/5))이 "가능" 이라
답만 하고 설치는 하지 않은 상태에서 시작했다 — `~/.hermes` 조차 없었다.

## What Shipped

**DGX (`aitopatom-36a9`)**

- Hermes Agent **v0.21.2** 설치. `~/.hermes`, `~/.local/bin/hermes`, managed Node
  v26.8.2 (`~/.hermes/node`), managed uv (`~/.hermes/bin/uv`). 전부 per-user, sudo 없음.
- `config/targets/dgx-spark.env` 신규. `HERMES_REMOTE_HOST=bobeenlee@100.103.30.62`.
- 기본 프로필에 Mac jarvis 의 model/provider 체인 이식:
  primary `custom:llama-local` @ `127.0.0.1:8080/v1` (qwen3.8-27b, ctx 65536),
  fallback altalt → openrouter → groq, vision `gemini-3.6-flash`.
  `hermes config migrate` 로 `_config_version` 0 → 44.
- macOS 전용 MCP 서버 3종(`cua-driver`, `antigravity-worker`, `openhuman-kakaotalk`)은
  **지우지 않고** `enabled: false` + `agent.disabled_toolsets` 로 꺼 뒀다. Linux 대응물이
  생기면 경로만 갈아끼우고 켠다.
- 게이트웨이 = systemd user unit `hermes-gateway.service`, active/enabled, linger yes.
- Kanban 보드 생성. alias 래퍼 `~/.local/bin/dgx-jarvis`.
- 작업 루트 `~/Workspaces/hermes-workspace` 클론 (https, read-only).

**hermes Mac (`bobeen`)**

- 2026-08-29 에 삭제됐던 `product` 프로필을
  `~/.hermes/backups/pre-update-2026-08-29-163521.zip` 에서 806 파일 복구 →
  `hermes profile rename product mac-jarvis`. `_config_version` 33 → 39.
- `mac-jarvis` 의 `DISCORD_HOME_CHANNEL` / `ALLOWED_CHANNELS` / `HOME_CHANNEL_NAME` 을
  **비웠다.** 복구본은 …3051 을 가리키는데 그 채널은 DGX 가 가져간다. 봇 토큰
  (`6fd532…`, jarvis 의 `9ff5af…` 와 다른 봇)은 유지 — 채널만 넣으면 붙는다.

**repo**

- `bin/hermes-remote:51` `HERMES_REMOTE_PATH` 기본값에 `~/.hermes/node/bin` 추가.
- `bin/hermes-remote` 의 Hallmark 명령 7곳이 하드코딩하던 `product` 를
  `HERMES_HALLMARK_PROFILE`(기본 `mac-jarvis`)로 치환. 그 프로필이 2주 전 삭제된 뒤로
  이 명령들은 죽어 있었다.
- `scripts/hermes/doctor.sh` 에 systemd 분기 추가 (launchd plist 검사와 같은 가드 모양).
- `dgx-spark-example.env`·`linux-target-profile.md` 의 죽은 vLLM/8000 예시 정정.

## Verification

```
check-ssh                ok
status                   target_os=linux service_manager=systemd computer_use_backend=none
model-status             custom:llama-local, 127.0.0.1:8080/v1
check-llm-endpoint       /v1/models 응답
run "Reply with exactly: OK"   → OK
setup-kanban             board created
setup-computer-use       exit 2  computer_use is unsupported for this target.
grant-computer-use       exit 2
verify-computer-use      exit 2
doctor.sh                systemd_gateway_active=active / enabled / linger=yes
```

## Not Done - 사람이 해야 하는 단계

1. **DGX `~/.hermes/.env` 에 키 입력** (파일 복사 금지, 시크릿 정책).
   `GEMINI_API_KEY` `GOOGLE_API_KEY` `GROQ_API_KEY` `OPENROUTER_API_KEY`
   `CLOUDFLARE_ACCOUNT_ID` `CLOUDFLARE_API_TOKEN`, 그리고 altalt 의 `X-Machine-ID`
   (`hermes config set custom_providers` 로 넣은 항목에 빈 값으로 남겨 뒀다).
   현재 DGX 는 로컬 LLM 만으로 돌고 fallback 은 전부 미인증 상태다.
2. **Discord 신원 컷오버.** 순서를 지켜야 한다 — websocket 소비자는 하나여야 한다.
   ```bash
   ssh bobeen 'launchctl bootout gui/$(id -u)/ai.hermes.gateway-jarvis'
   ssh bobeen 'launchctl list | grep gateway-jarvis'          # 사라져야 한다
   # DGX ~/.hermes/.env 에 jarvis 봇 토큰 + HOME/ALLOWED=…3051, IGNORED=…9918
   HERMES_TARGET=config/targets/dgx-spark.env bin/hermes-remote gateway-restart
   ```
   Mac 의 `~/.hermes/profiles/jarvis/` 는 지우지 않는다 — 메신저 비서가 그
   `config.yaml`(`messenger_assistant.py:667`)과 `.env` 의 봇 토큰(`:1711`)을 계속 읽는다.
   컷오버 직후 Discord 에 "메신저 비서 자동 종료" 가 뜬다 —
   `messenger_assistant.py:1840` 의 `gateway_identity()` 가 설계대로 fail-closed 로
   전환한 것이다. …9918 채널에 `메신저 시작` 으로 복구한다. 한 번만 트립한다.

## Not Verified

- 게이트웨이 장기 안정성, 호스트 재부팅 후 복귀.
- 로컬 LLM(qwen3.8-27b, 약 26GB)과 ComfyUI 동시 적재 시 메모리 압박. 이번 기동 시점에는
  ComfyUI 큐가 비어 있었고 가용 메모리는 115GB 였다.
- `mac-jarvis` 의 product 봇(`6fd532…`)이 Discord 에서 아직 살아 있는지. 채널을 비워
  뒀으므로 이번에는 드러나지 않는다.
- 복구된 `skill-sources/hallmark` 는 파일만 있고 `.git` 이 없다 — 백업 zip 이 모든 `.git`
  디렉터리를 제외했다. `check-hallmark-update` 가 그걸 보고한다. `setup-hallmark` 로
  재생성 가능.

## Remote State Changed

| 대상 | 변경 | 되돌리기 |
| --- | --- | --- |
| DGX `~/.hermes` | 신규 설치 (Hermes v0.21.2, node, uv, venv) | `hermes uninstall` 또는 디렉터리 삭제 |
| DGX `hermes-gateway.service` | user unit 설치·기동·enable | `hermes gateway uninstall` |
| DGX `llama-local.service` | 기동 (boot enable 은 **안 했다**) | `dgx-ai-control --service llama --action stop` |
| DGX `~/Workspaces/hermes-workspace` | 클론 | 디렉터리 삭제 |
| Mac `~/.hermes/profiles/mac-jarvis` | 복구 + 개명 | `hermes profile delete mac-jarvis` |
| Mac `~/.hermes/profiles/.deleted/product` | tombstone 제거 | 파일 재생성 |

`ai.hermes.gateway-jarvis` 는 **아직 내리지 않았다.** 컷오버는 위 "사람이 해야 하는
단계" 2번에서 한다.

## 옆에서 발견한 것 (이번 범위 밖)

Mac 의 `ai.hermes.kakao-ai-chat` 이 exit 255 로 플래핑한다. 선행 세션의 repo 이름 변경
수습이 끊긴 흔적으로 보인다. 이 작업은 건드리지 않았다.
