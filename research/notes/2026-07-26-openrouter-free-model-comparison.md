---
type: ResearchNotes
title: OpenRouter 무료 모델 비교 조사 노트
timestamp: 2026-07-26T16:45:00+09:00
tags: [openrouter, hermes, benchmark, uncertainty]
---

# 관찰

## 원격 상태

- `bin/hermes-remote check-ssh`: 성공
- `bin/hermes-remote status`: Hermes Agent v0.19.0, 기본 모델 `openai/gpt-5-nano`, provider `custom:altalt`
- 원격 설정은 읽기만 했고 변경하지 않았다.

## OpenRouter 실시간 API

| 모델 | 2026-07-26 상태 | 가격 | OpenRouter 컨텍스트 | 최대 출력 | 제공자/양자화 | 주요 파라미터 |
|---|---|---:|---:|---:|---|---|
| `poolside/laguna-s-2.1:free` | 가용 | $0/$0 | 262,144 | 32,768 | Poolside/FP8 | reasoning, tools, tool_choice |
| `poolside/laguna-m.1:free` | 가용, 7/28 종료 예정 | $0/$0 | 262,144 | 32,768 | Poolside/FP4 | reasoning, tools, tool_choice |
| `nvidia/nemotron-3-super-120b-a12b:free` | 가용 | $0/$0 | 262,144 | 262,144로 광고됨 | NVIDIA/미표기 | reasoning_effort, tools, structured_outputs |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 가용 | $0/$0 | 1,000,000 | 65,536 | NVIDIA/미표기 | reasoning_effort, tools |

Super의 최대 출력 262,144 표시는 총 컨텍스트와 같은 값이어서 실제 긴 출력 허용량으로 단정하지 않는다.

## Hermes 선택기와 OpenRouter의 차이

- 공식 Hermes 원격 카탈로그 `updated_at=2026-07-24T19:06:06Z`에는 무료형으로 M.1, Nemotron Super, Nemotron Ultra가 있다.
- `poolside/laguna-s-2.1:free`는 아직 큐레이션에 없다.
- 원격 캐시도 같은 카탈로그를 담고 있다.
- 원격 코드에서 `fetch_openrouter_models()`는 먼저 Hermes 큐레이션 목록을 가져온 뒤 OpenRouter 실시간 API에서 존재 여부와 `tools` 지원을 확인한다. 실시간 API에만 있는 모델은 자동 추가하지 않는다.
- 원격에서 실제 함수 출력:

```text
[('poolside/laguna-m.1:free', 'free'),
 ('nvidia/nemotron-3-super-120b-a12b:free', 'free'),
 ('nvidia/nemotron-3-ultra-550b-a55b:free', 'free')]
```

따라서 S 2.1 무료형은 **OpenRouter에는 있지만 현재 원격 Hermes 선택기에는 없다**.

# 공식 측정치

수치는 모두 각 공급자의 자체 보고이며, 동일 행에 놓여도 하네스·스캐폴드·벤치마크 버전·reasoning budget이 다를 수 있다.

## 현재 GPT-5 nano

- 400K 컨텍스트, 128K 최대 출력, 이미지 입력, function calling, structured outputs 지원
- OpenAI 직접 API 정가: 입력 $0.05/M, 출력 $0.40/M
- OpenAI의 `high` reasoning 측정:
  - SWE-bench Verified 54.7%
  - Aider Polyglot 48.4%
  - GPQA Diamond 71.2%
  - HLE 8.7%
  - AIME 2025 85.2%
  - Tau²-bench airline/retail/telecom 41.0%/62.3%/35.5%
  - 256K MRCR 34.9%, BrowseComp Long Context 256K 68.4%
- 현재 `altalt`가 OpenAI 원본 API와 같은 reasoning 설정·스냅샷·라우팅을 쓰는지는 확인되지 않았다.

## Laguna M.1

- 225B total / 23B active, 네이티브 262K, agentic coding 전용
- Poolside `pool` 하네스, thinking enabled, 최대 500 steps:
  - SWE-bench Verified 74.6%
  - SWE-bench Multilingual 63.1%
  - SWE-Bench Pro 49.2%
  - Terminal-Bench 2.0 45.8%
- 일부 태스크 이미지와 verifier를 신뢰성 문제 때문에 패치했다.
- OpenRouter 무료 제공은 FP4이므로 BF16 모델 카드 점수의 재현을 보장하지 않는다.

## Laguna S 2.1

- 118B total / 8B active, 네이티브 1M, reasoning/tool calling
- Poolside `pool` 하네스, max thinking:
  - Terminal-Bench 2.1 70.2%
  - SWE-bench Multilingual 78.5%
  - SWE-Bench Pro 59.4%
  - DeepSWE 40.4%
  - SWE Atlas 46.2%
  - Toolathlon Verified 49.7%
- M.1과 이름·데이터셋이 같은 항목에서는 SWE Multilingual +15.4%p, SWE-Bench Pro +10.2%p.
- Poolside는 Hermes 같은 제3자 하네스에서 첫 도구 호출이 스키마를 잘못 기억할 수 있고, 중첩 JSON 인자를 잘못 escape할 수 있다고 명시한다.
- OpenRouter 무료 제공은 FP8, 262K/32K로 네이티브 1M BF16 제공과 다르다.

## Nemotron 3 Super

- 120B total / 12B active, 원본 최대 1M, OpenRouter 무료형은 262K
- 공식 지원 언어 목록에 한국어는 없음.
- NVIDIA 카드:
  - GPQA no tools 79.23
  - HLE no tools 18.26
  - MMLU-Pro 83.73
  - LiveCodeBench v5 81.19
  - SWE-Bench OpenHands 60.47
  - Terminal Bench Core 2.0 31.00
  - RULER 256K/1M 96.30/91.75
- OpenRouter 무료형은 네 모델 중 유일하게 `structured_outputs`와 `response_format`을 명시적으로 광고한다.

## Nemotron 3 Ultra

- 550B total / 55B active, OpenRouter 1M, 한국어 공식 지원
- NVIDIA 카드:
  - GPQA no tools 87.0
  - HLE no tools 26.7
  - MMLU-Pro 86.8
  - LiveCodeBench v6 89.0
  - SWE-Bench Verified 70.7
  - Terminal Bench 2.1 56.4
  - RULER 1M 94.7
  - MMLU-ProX 10개 언어 평균 83.0
- Poolside의 같은 2026-07-21 표에서는 S 2.1이 Ultra보다 Terminal-Bench 2.1 +13.8%p, SWE-bench Multilingual +10.8%p, Toolathlon Verified +15.4%p 높다. 다만 표는 공급자·벤치마크·제3자 보고 중 최대치를 섞은 비교이다.

# 해석

- 코딩 에이전트 장기 작업: 공식 자기보고 측정은 Laguna S 2.1이 가장 인상적이다. 하지만 현재 picker 미노출과 Hermes 도구 스키마 한계가 있다.
- 현재 picker 안에서 코딩 우선: M.1 공식 SWE-bench 74.6%는 GPT-5 nano의 54.7%보다 높지만, M.1 무료형은 7/28 종료되고 평가 하네스도 다르다.
- 범용 추론·한국어·긴 문맥: Ultra가 가장 강한 후보다. 1M OpenRouter 컨텍스트와 한국어 지원이 명시되어 있다.
- 경량 agent·구조화 출력: Super가 실용적이다. 공식 지식·추론 점수는 GPT-5 nano보다 대체로 높지만 한국어 지원이 공식 목록에 없다.
- 안정적 기본값: GPT-5 nano는 무료가 아니지만 OpenAI 공식 function calling/structured outputs, 이미지 입력, 400K/128K와 비교적 명확한 API 계약이 장점이다.

# 반대 증거와 불확실성

- 벤치마크 숫자는 OpenRouter 무료 endpoint 자체의 실측이 아니다.
- Laguna와 NVIDIA 카드 점수는 공급자 자체 보고이고 일부 agent 벤치는 내부 또는 수정된 하네스를 사용한다.
- Terminal-Bench, LiveCodeBench, TauBench는 모델별 버전이 달라 숫자를 직접 비교하면 안 된다.
- OpenAI GPT-5 nano 점수는 OpenAI 하네스와 `high` reasoning 기준이며 `altalt` 경유 설정과 같다는 증거가 없다.
- 무료 모델은 용량·속도·rate limit·데이터 정책·종료일이 바뀔 수 있다.
- OpenRouter 무료 Poolside/NVIDIA 페이지는 입력·출력이 모델 개선에 사용될 수 있음을 고지한다. 비밀·개인정보·사내 코드·운영 로그에는 부적합하다.

# 설정 변경

없음.
