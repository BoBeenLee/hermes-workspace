# hermes mac 로컬 MLX 모델 Qwen3.6-27B → Qwen3.8-27B 교체

- Task type: `remote-config` (launchd 서빙 대상 + provider 모델명)
- HIL status: `n/a` (직접 요청)
- Target: `bobeenlee@bobeen` (`bobeen-macbookpro-2`, MacBookPro18,1, 32GB, macOS 26.5.2)
- Branch/worktree: `none` for remote operations
- Completion mode: `review-required`
- 선행 작업: `tasks/2026-08-21-hermes-mac-qwen3.6-27b-mlx.md`
- Plan: `~/.claude/plans/hermes-mac-qwen3-6-27b-4-bit-snuggly-rabbit.md`

## Requested Outcome

로컬 MLX 슬롯(`127.0.0.1:8080`, provider `custom:mlx-qwen`)의 모델을
`lmstudio-community/Qwen3.8-27B-MLX-4bit`로 올리고, 검증 후
`lmstudio-community/Qwen3.6-27B-MLX-4bit` 캐시를 제거한다. 프로필 라우팅과 fallback
순서는 그대로 둔다.

## Why It Was A Drop-in

3.8 4bit는 3.6 4bit와 아키텍처가 동일하다: `Qwen3_5ForConditionalGeneration`,
`model_type=qwen3_5`, layer `64`, KV head `4`, head_dim `256`, vocab `248320`,
4bit group `64`, 가중치 `16.1GB` / 3 shard. 따라서 mlx-lm `0.31.3`이 그대로 로드하고
메모리 상한 플래그도 재사용했다. chat template은 `enable_thinking`과 tool call을 계속
지원한다.

## Remote Changes

- 다운로드: `lmstudio-community/Qwen3.8-27B-MLX-4bit`, snapshot
  `6067b15cf581666a4aecf6af3afaba4bb5efc20c`, safetensors 3 × 5.0GB
  (`15336MB` on disk), incomplete blob 0개.
- 심볼릭 링크 `~/Workspaces/local-llm/models/qwen3.8-27b-mlx` 추가.
- `scripts/start-mlx-qwen.sh`의 `--model` 경로만 3.8로 교체. 메모리 상한 플래그
  (`--prompt-cache-size 1`, `--prompt-cache-bytes 4294967296`,
  `--decode-concurrency 1`, `--prompt-concurrency 1`, `--prefill-step-size 512`,
  `--max-tokens 4096`, `--chat-template-args '{"enable_thinking":false}'`)는 유지.
- `scripts/smoke-test-mlx-qwen.sh` 기본 `MODEL`을 3.8로 교체.
- `launchctl kickstart -k gui/$UID/ai.hermes.mlx-qwen`.
- Hermes config 3개에서 모델 문자열만 전량 치환(파일당 3곳: `model.default`,
  `custom_providers.mlx-qwen.model`, `models:` 맵 키). provider 이름, base_url,
  `context_length: 65536`, fallback 순서는 미변경.
  - `~/.hermes/config.yaml`
  - `~/.hermes/profiles/jarvis/config.yaml`
  - `~/.hermes/profiles/preflight/config.yaml`
- gateway 재시작: default, jarvis, preflight.
- 제거: `models/qwen3.6-27b-mlx` 심볼릭 링크와
  `~/.cache/huggingface/hub/models--lmstudio-community--Qwen3.6-27B-MLX-4bit` (15GB 회수).

### Backups

```text
/Users/bobeenlee/Workspaces/local-llm/scripts/start-mlx-qwen.sh.bak-qwen38-20260821-131054
/Users/bobeenlee/Workspaces/local-llm/scripts/smoke-test-mlx-qwen.sh.bak-qwen38-20260821-131054
/Users/bobeenlee/.hermes/config.yaml.bak-qwen38-20260821-131253
/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.bak-qwen38-20260821-131253
/Users/bobeenlee/.hermes/profiles/preflight/config.yaml.bak-qwen38-20260821-131253
```

## Verification

- `smoke-test-mlx-qwen.sh`: `/v1/models`와 `/chat/completions` 통과. 8080은
  `127.0.0.1`만 LISTEN.
- 성능(고정 프롬프트 256토큰 3회 median): `25.02s`, `10.23 tok/s`.
  3.6 기준값 `24.84s` / `10.30 tok/s`와 동일 수준 — 구조가 같으므로 예상된 결과.
- 라우팅(`hermes fallback list` 및 wrapper)
  - `default`/`jarvis`: primary 3.8 → `custom:altalt` `openai/gpt-5-nano` →
    OpenRouter `poolside/laguna-s-2.1:free` → Groq `openai/gpt-oss-120b`
  - `preflight`: primary 3.8 → OpenRouter `poolside/laguna-s-2.1:free`
  - `content`: `groq` `openai/gpt-oss-120b` (미변경)
- 프로필 응답: `preflight`, `jarvis` 모두 `OK`. 삭제 후 `preflight` 재확인도 `OK`.
- 툴 콜: default 프로필에서 파일 읽기 툴로 `README.md`를 읽고 정확한 내용 기반 요약
  생성. 3.6과 달리 5줄 인용은 생략하고 요약만 출력했으나 툴 실행 자체는 정상.
- 안정성: Metal OOM 카운트 `2`로 불변(둘 다 3.6 작업 시점의 기본 플래그 사고),
  새 `Python-*.ips` 크래시 리포트 없음, launchd PID 유지.
- `bin/hermes-remote status`: 5개 gateway 모두 launchd 감시, kanban 통계 베이스라인과
  동일. `verify-computer-use` 체크 마크 베이스라인과 동일, `verify-hallmark`,
  `dashboard-status` 이상 없음.
- gateway 에러 로그(13시대)에는 Discord command 등록 `429` 경고 1건만 있고 provider
  관련 예외 없음.
- 로컬 `tests/test_messenger_assistant.py`: 117 tests OK.
- 삭제 후 `/v1/models`에는 3.8만 남음. HF 캐시 총량 `15G`.

## Notes

- MTP 드래프트(`mlx-community/Qwen3.8-27B-MTP-4bit`)는 `model_type=qwen3_5_mtp`이고
  mlx-lm 0.31.3에 해당 모듈이 없어 `--draft-model`로 쓸 수 없다. speculative decoding
  으로 속도를 올리려면 mlx-lm 업그레이드나 MTPLX 계열 self-contained 변환본이 필요하다.
- `content`/`product`의 `413 payload too large`는 이번 변경과 무관한 기존 증상.

## Rollback

3.6 캐시는 삭제됐으므로 되돌리려면 재다운로드가 선행된다.

1. `hf download lmstudio-community/Qwen3.6-27B-MLX-4bit`
2. `models/qwen3.6-27b-mlx` 심볼릭 링크 재생성
3. `scripts/start-mlx-qwen.sh`를 `.bak-qwen38-20260821-131054`로 복원
4. 세 config.yaml을 `.bak-qwen38-20260821-131253`으로 복원
5. `launchctl kickstart -k gui/$(id -u)/ai.hermes.mlx-qwen`
6. `bin/hermes-remote gateway-restart`, `jarvis gateway restart`,
   `preflight gateway restart`

## Checks Run

```text
bin/hermes-remote check-ssh | status | gateway-restart
bin/hermes-remote verify-computer-use | verify-hallmark | dashboard-status
hermes/jarvis/preflight/content fallback list
hermes -z (tool call) | jarvis -z | preflight -z
scripts/smoke-test-mlx-qwen.sh
POST /v1/chat/completions (256-token bench x3)
python3 -m unittest discover -s tests -p test_messenger_assistant.py
python3 scripts/hermes/validate_okf.py
```
