# hermes mac Qwen3.6-27B 4-bit MLX 전환

- Task type: `remote-config` (launchd + provider 변경)
- HIL status: `n/a` (직접 요청)
- Target: `bobeenlee@bobeen` (`bobeen-macbookpro-2`, MacBookPro18,1, 32GB, macOS 26.5.2) through Tailscale SSH
- Branch/worktree: `none` for remote operations
- Completion mode: `review-required`
- Status: 로컬 27B 전환 완료. 35B 캐시 삭제만 승인 대기
- Plan: `~/.claude/plans/hermes-mac-qwen3-6-27b-4-bit-snuggly-rabbit.md`

## Requested Outcome

`lmstudio-community/Qwen3.6-27B-MLX-4bit`를 hermes mac에 설치해 로컬 MLX 슬롯
(`127.0.0.1:8080`, `custom:mlx-qwen`)의 모델을 27B로 교체하고, 기존
`samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed`는 호스트에서 제거한다.
`default`/`jarvis`/`preflight` 프로필의 primary를 로컬 27B로 바꾸고 직전 primary를
바로 다음 순위 fallback으로 내린다. `content`/`product`는 변경하지 않는다.

## Remote Changes

- 모델 다운로드: `lmstudio-community/Qwen3.6-27B-MLX-4bit`, 16 files,
  safetensors 3 shard × 5.0GB (`15G` on disk), snapshot
  `bd83f6fe15b171f1549475db2348389c0f541c21`. incomplete blob 0개.
- 심볼릭 링크 추가: `~/Workspaces/local-llm/models/qwen3.6-27b-mlx` → 위 snapshot.
- `~/Workspaces/local-llm/scripts/start-mlx-qwen.sh`를 27B로 교체하고 메모리
  상한 플래그 추가. `~/Workspaces/local-llm/scripts/smoke-test-mlx-qwen.sh`의
  기본 MODEL도 27B로 교체.
- launchd `ai.hermes.mlx-qwen` 재적용. plist 자체는 스크립트를 실행하므로 내용
  변경 없음(백업만 생성).
- Hermes config 3개 편집: `~/.hermes/config.yaml`,
  `~/.hermes/profiles/jarvis/config.yaml`,
  `~/.hermes/profiles/preflight/config.yaml`.
  - `model:` primary를 `custom:mlx-qwen` / 27B / `http://127.0.0.1:8080/v1` /
    `chat_completions` / `context_length: 65536`로.
  - `default`/`jarvis`의 `fallback_providers` 최상단에
    `provider: custom:altalt`, `model: openai/gpt-5-nano` 삽입.
  - `custom_providers`의 `mlx-qwen` 모델명을 27B로. jarvis 프로필에는
    `mlx-qwen` 정의가 아예 없었으므로 새로 추가.
- gateway 재시작: default, jarvis, preflight.

### Backups

```text
/Users/bobeenlee/Workspaces/local-llm/scripts/start-mlx-qwen.sh.bak-qwen27b-20260821-120406
/Users/bobeenlee/Library/LaunchAgents/ai.hermes.mlx-qwen.plist.bak-qwen27b-20260821-120406
/Users/bobeenlee/.hermes/config.yaml.bak-qwen27b-20260821-120741
/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.bak-qwen27b-20260821-120741
/Users/bobeenlee/.hermes/profiles/preflight/config.yaml.bak-qwen27b-20260821-120741
/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.bak-qwen27b-mlxprovider
```

## Serving Configuration

```text
mlx_lm.server --model /Users/bobeenlee/Workspaces/local-llm/models/qwen3.6-27b-mlx
  --host 127.0.0.1 --port 8080 --max-tokens 4096
  --prompt-cache-size 1 --prompt-cache-bytes 4294967296
  --decode-concurrency 1 --prompt-concurrency 1 --prefill-step-size 512
  --chat-template-args '{"enable_thinking":false}'
```

- mlx-lm `0.31.3`, mlx `0.31.2`, Homebrew python 3.10 site-packages. 업그레이드
  불필요(`mlx_lm/models/qwen3_5.py` 이미 포함).
- 모델은 dense 27B VLM(`Qwen3_5ForConditionalGeneration`, `model_type=qwen3_5`).
  Hermes는 텍스트 경로만 쓰고 vision은 기존 auxiliary 체인이 담당한다.

## Incidents

`mlx_lm.server` 기본값으로 첫 Hermes 에이전트 실행 중 두 번 abort 했다.

```text
libc++abi: terminating due to uncaught exception of type std::runtime_error:
[METAL] Command buffer execution failed: Insufficient Memory
```

- 크래시 리포트: `Python-2026-08-21-121425.ips`, `Python-2026-08-21-121927.ips`
  (macOS "Python이 예기치 않게 종료됨" 다이얼로그의 정체).
- 원인: 가중치 `16.1GB` + KV 토큰당 약 `0.25MB`(64 layer × 4 KV head × head_dim
  256)에 기본 `--prompt-cache-size 10`, `--decode-concurrency 32`,
  `--prompt-concurrency 8`이 겹쳐 32GB 호스트의 GPU wired limit 초과.
  기존 35B-A3B는 KV가 토큰당 `0.08MB`라 같은 기본값에서 문제가 없었다.
- 조치: 위 상한 플래그 적용(12:20:37 재시작). 이후 추가 abort·크래시 리포트 없음.

Hermes는 `context_length` 32768을 거부한다("below the minimum 64000 required").
그래서 선언값은 `65536`이며, 실제로 64k를 채우면 KV만 약 `16.4GB`가 되어 32GB
호스트에서는 스왑 압력이 생길 수 있다. 상한 플래그가 캐시를 4GiB로 묶어 이
경로를 완화한다.

## Verification

- `/v1/models`: 27B 이름과 snapshot 경로 반환. 8080은 `127.0.0.1`만 LISTEN.
- 콜드 로드 + 첫 응답: `5.6s`.
- 프로필 실사용: `default`, `jarvis`, `preflight` 모두 로컬 27B로 정상 응답.
  `jarvis`는 provider 정의 추가 전에는 `Unknown provider 'custom:mlx-qwen'`으로
  실패했고, 추가 후 통과.
- 툴 콜: default 프로필에서 파일 읽기 툴 실행 후 요약까지 성공
  (`README.md` 5줄 인용 + 1문장 요약). reasoning 토큰 누출 없음.
- `hermes fallback list` 확인
  - `default`/`jarvis`: primary 27B → `custom:altalt` `openai/gpt-5-nano` →
    OpenRouter `poolside/laguna-s-2.1:free` → Groq `openai/gpt-oss-120b`
  - `preflight`: primary 27B → OpenRouter `poolside/laguna-s-2.1:free`
  - `content`: `groq` `openai/gpt-oss-120b` (변경 없음)
- `bin/hermes-remote status`: 5개 gateway 모두 launchd 감시 상태, kanban 통계
  베이스라인과 동일. 12:00 이후 gateway error 로그 없음.
- `verify-computer-use` 출력의 체크 마크가 베이스라인과 동일, `dashboard-status`
  와 `verify-hallmark` 이상 없음.
- 로컬 `tests/test_messenger_assistant.py`: 117 tests OK.
- 성능(고정 프롬프트, 256 토큰, 3회 median)
  - 35B-A3B(변경 전): `6.38s`, `40.10 tok/s`
  - 27B dense(변경 후): `24.84s`, `10.30 tok/s` → 약 `3.9x` 느림
- `content`/`product`의 `413 payload too large`는 이번 변경과 무관한 기존 증상
  (`~/.hermes/profiles/content/logs/errors.log`에 2026-06-20, 2026-07-08 기록).

## Pending

35B 캐시 삭제는 auto mode 분류기가 차단해 실행하지 못했다. 승인 후 실행할 명령:

```bash
ssh bobeen 'rm -f ~/Workspaces/local-llm/models/qwen3.6-35b-a3b-mlx && rm -rf ~/.cache/huggingface/hub/models--samuelfaj--Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed'
```

`19G` 회수. 삭제 후에는 35B 롤백 시 재다운로드가 필요하다. config·plist·start
script·smoke script에는 이미 35B 참조가 없다.

## Rollback

1. 세 config.yaml을 `.bak-qwen27b-20260821-120741`로 복원(jarvis는
   `.bak-qwen27b-mlxprovider`가 mlx-qwen 정의 추가 직전 상태).
2. `start-mlx-qwen.sh`를 `.bak-qwen27b-20260821-120406`으로 복원.
3. `launchctl kickstart -k gui/$(id -u)/ai.hermes.mlx-qwen`.
4. `bin/hermes-remote gateway-restart`, `jarvis gateway restart`,
   `preflight gateway restart`.
5. 35B 캐시가 삭제된 뒤라면 `hf download samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed`
   와 `models/qwen3.6-35b-a3b-mlx` 심볼릭 링크 재생성이 선행되어야 한다.

## Checks Run

```text
bin/hermes-remote check-ssh | status | model-status | gateway-restart
bin/hermes-remote run | verify-computer-use | dashboard-status | verify-hallmark
hermes fallback list (default, jarvis, preflight, content)
hermes -z / jarvis -z / preflight -z / content -z / product -z
GET  http://127.0.0.1:8080/v1/models
POST http://127.0.0.1:8080/v1/chat/completions (smoke, 256-token bench x3)
scripts/smoke-test-mlx-qwen.sh
python3 -m unittest discover -s tests -p test_messenger_assistant.py
python3 scripts/hermes/validate_okf.py
```
