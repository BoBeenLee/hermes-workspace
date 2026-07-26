---
type: ResearchReport
title: OpenRouter 무료 모델과 현재 GPT-5 nano 비교
timestamp: 2026-07-26T16:45:00+09:00
tags: [openrouter, hermes, laguna, nemotron, gpt-5-nano]
---

# 결론

`poolside/laguna-s-2.1:free`는 **OpenRouter에는 현재 존재하고 가용**하다. 무료 endpoint는 FP8, 262K 컨텍스트, 32K 최대 출력이며 reasoning과 tool calling을 지원한다.

그러나 **기본 원격 Mac의 현재 Hermes 모델 선택기에는 아직 나오지 않는다.** Hermes는 OpenRouter 전체 무료 목록이 아니라 NousResearch가 큐레이션한 목록을 먼저 적용하며, 2026-07-24 카탈로그와 원격 캐시에는 기존 무료 3개만 있다.

현재 선택기 안에서의 추천은 다음과 같다.

1. **한국어·범용 추론·장문:** `nvidia/nemotron-3-ultra-550b-a55b:free`
2. **코딩 에이전트:** `poolside/laguna-m.1:free`, 단 2026-07-28 종료 예정이라 단기 후보
3. **가벼운 에이전트·구조화 출력:** `nvidia/nemotron-3-super-120b-a12b:free`
4. **운영 안정성·명확한 API 계약:** 현재 `openai/gpt-5-nano` 유지

S 2.1이 Hermes 큐레이션에 추가되면 코딩 에이전트용 1순위 실험 후보지만, Poolside가 Hermes 도구 스키마 적응 문제를 공식 한계로 직접 언급한다.

# 가용성 스냅샷

| 모델 | OpenRouter 무료 | 현재 Hermes picker | OR 컨텍스트/출력 | 운영 메모 |
|---|---|---|---|---|
| `poolside/laguna-s-2.1:free` | 예 | 아니오 | 262K/32K | FP8, 신규, Hermes tool schema 한계 |
| `poolside/laguna-m.1:free` | 예 | 예 | 262K/32K | FP4, 7/28 종료 예정 |
| `nvidia/nemotron-3-super-120b-a12b:free` | 예 | 예 | 262K/최대 출력 표기 불명확 | 구조화 출력 광고, 한국어 미명시 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 예 | 예 | 1M/65K | 한국어 지원, 가장 큰 문맥 |
| `openai/gpt-5-nano` via altalt | 무료 아님/현재 사용 중 | 현재 기본값 | 공식 원본 400K/128K | altalt 중계 동등성 미확인 |

# 성능 비교

## 코딩·에이전트

공식 자기보고 수치에서:

- GPT-5 nano: SWE-bench Verified 54.7%, Aider Polyglot 48.4%
- Laguna M.1: SWE-bench Verified 74.6%, SWE-Bench Pro 49.2%
- Nemotron Super: SWE-Bench OpenHands 60.47%
- Nemotron Ultra: SWE-bench Verified 70.7%
- Laguna S 2.1: Terminal-Bench 2.1 70.2%, SWE-Bench Pro 59.4%, SWE-bench Multilingual 78.5%

표면적인 숫자만 보면 Laguna 계열과 Ultra가 GPT-5 nano보다 강하다. 하지만 공급자별 agent harness, task patch, reasoning budget, benchmark 버전이 달라 동일 시험의 정면 대결로 보면 안 된다. 특히 OpenRouter 무료형의 양자화 endpoint를 직접 측정한 점수가 아니다.

Poolside 자체의 같은 릴리스 표에서는 S 2.1이 Ultra보다 Terminal-Bench 2.1에서 70.2 대 56.4, SWE-bench Multilingual에서 78.5 대 67.7로 높았다. 동시에 Poolside는 제3자 harness 간 비교 가능성이 낮다고 설명한다.

## 범용 추론

겹치는 공식 no-tools 지표:

| 지표 | GPT-5 nano | Nemotron Super | Nemotron Ultra |
|---|---:|---:|---:|
| GPQA | 71.2 | 79.23 | 87.0 |
| HLE | 8.7 | 18.26 | 26.7 |

공급자 자체 측정 기준으로는 Ultra, Super, GPT-5 nano 순이다. 같은 데이터셋 이름이어도 평가 설정이 완전히 같다고 확인되지 않았으므로 방향성 증거로만 사용해야 한다.

## 한국어·긴 문맥

- Ultra는 한국어를 공식 지원하며 OpenRouter endpoint가 1M 컨텍스트를 제공한다.
- Super 원본 모델은 최대 1M이지만 OpenRouter 무료 endpoint는 262K이고 공식 지원 언어에 한국어가 없다.
- GPT-5 nano 공식 원본은 400K이며 OpenAI 최신 모델 공통으로 다국어·이미지 입력을 지원한다.
- Laguna 모델 카드는 소프트웨어 엔지니어링 중심이고 한국어를 명시적으로 보장하지 않는다.

# 모델별 판단

## `nvidia/nemotron-3-ultra-550b-a55b:free`

현재 3개 선택 가능 무료 모델 중 품질 우선 추천이다. 공식 카드에서 Super보다 지식·추론·instruction following·장문 점수가 전반적으로 높고, 한국어와 1M 컨텍스트가 명시된다. 단 OpenRouter 무료 경로의 양자화 방식이 공개되지 않았고 입력 세션 기록 가능성이 있다.

## `poolside/laguna-m.1:free`

코딩 전용으로는 매력적이지만 7월 28일 종료 예정이라 기본 모델로 옮기기에는 수명이 너무 짧다. 공식 SWE-bench 수치는 높지만 Poolside 하네스, patched task 환경, thinking enabled 결과이며 OpenRouter FP4 경로 재현치는 아니다.

## `nvidia/nemotron-3-super-120b-a12b:free`

12B active로 Ultra보다 계산 효율 지향이다. OpenRouter가 구조화 출력 파라미터를 광고하는 것도 Hermes 도구 작업에 유리하다. 공식 추론 점수는 GPT-5 nano보다 높지만 한국어가 공식 지원 목록에 없고 OpenRouter 컨텍스트는 262K로 제한된다.

## 현재 `custom:altalt / openai/gpt-5-nano`

무료는 아니지만 function calling, structured outputs, 이미지 입력, 400K 컨텍스트와 128K 최대 출력이라는 공식 계약이 명확하다. OpenAI의 GPT-5 nano는 요약·분류·비용 민감 작업용 모델이라 고난도 코딩·추론에서는 위 대형 무료 모델의 자기보고 점수보다 낮다.

단, 현재 endpoint는 OpenAI 직접 API가 아니라 `altalt`이므로 실제 스냅샷, reasoning effort, 처리량, rate limit, 도구 호환성이 공식 OpenAI 수치와 같다고 단정할 수 없다.

## `poolside/laguna-s-2.1:free`

OpenRouter에는 이미 있다. 네이티브 모델은 118B-A8B에 1M 컨텍스트이고, 무료 endpoint는 FP8 262K/32K다. Poolside 공식 동일 벤치마크에서 M.1보다 SWE-bench Multilingual +15.4%p, SWE-Bench Pro +10.2%p 높아 후속 코딩 모델로 볼 근거가 있다.

다만 현재 Hermes picker에는 없고, Poolside가 다음 한계를 공개했다.

- Hermes 같은 제3자 harness에서 첫 tool schema를 기억에 의존해 잘못 호출할 수 있음
- 중첩 JSON tool argument escape 오류 가능
- max thinking에서 장시간 overthinking 가능

따라서 큐레이션 추가 후에도 운영 기본값으로 바로 전환하기보다 실제 Hermes 도구 호출 smoke test가 먼저다.

# 위험

- 무료 endpoint 가용성·rate limit·종료일은 변할 수 있다.
- 무료 Poolside/NVIDIA 사용 시 입력·출력이 모델 개선에 쓰일 수 있다. SSH 출력, 운영 로그, 사내 코드, 개인정보, 키나 토큰을 보내지 않아야 한다.
- 공급자 모델 카드 점수와 OpenRouter 무료 양자화 endpoint 성능은 동일하지 않을 수 있다.
- M.1은 2026-07-28 종료 예정이라 전환 비용을 들일 가치가 낮다.

# 다음 조사

- Hermes 공식 카탈로그에 `poolside/laguna-s-2.1:free`가 추가되는지 확인
- 추가 후 비민감 공개 코드로 tool-call, nested JSON, 장문 작업 smoke test
- 동일한 Hermes harness와 고정된 공개 태스크로 GPT-5 nano, S 2.1, Super, Ultra를 직접 비교

# 완료 메모

- task type: market-research
- HIL status: skipped (명확한 읽기 전용 조사)
- branch/worktree: none
- changed files: 연구 brief, source ledger, notes, report
- checks: 원격 SSH/status, OpenRouter live API, Hermes 실제 picker 함수, 공식 문서 교차검증
- source ledger: `research/sources/2026-07-26-openrouter-free-model-comparison.jsonl`
- completion mode: done
