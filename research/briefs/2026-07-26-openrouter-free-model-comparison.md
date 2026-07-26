---
type: ResearchBrief
title: OpenRouter 무료 에이전트 모델과 현재 GPT-5 nano 비교
timestamp: 2026-07-26T16:45:00+09:00
tags: [openrouter, hermes, laguna, nemotron, gpt-5-nano]
---

# 연구 질문

2026-07-26 KST 현재:

1. `poolside/laguna-s-2.1:free`가 OpenRouter에 존재하는가?
2. 기본 원격 Mac의 Hermes 모델 선택기에서 선택 가능한가?
3. Hermes 선택기에 노출되는 OpenRouter 무료 모델 3개와 현재 `custom:altalt / openai/gpt-5-nano`의 성능·기능·운영상 차이는 무엇인가?

# 범위

- 대상: 기본 원격 Mac `bobeen`
- 지역: 글로벌 API 가용성, 한국어 사용 관점 포함
- 시간 기준: 2026-07-26 16:45 KST
- 모델:
  - `poolside/laguna-s-2.1:free`
  - `poolside/laguna-m.1:free`
  - `nvidia/nemotron-3-super-120b-a12b:free`
  - `nvidia/nemotron-3-ultra-550b-a55b:free`
  - 현재 설정 `openai/gpt-5-nano` via `custom:altalt`

# 증거 기준

- OpenRouter 실시간 공개 API와 공식 모델 페이지
- NousResearch Hermes 공식 모델 카탈로그와 원격 호스트의 실제 캐시/선택기 함수 출력
- Poolside, NVIDIA, OpenAI의 공식 모델 카드·기술 보고서·출시 글
- 공급자 자기보고 벤치마크는 측정치로 기록하되, 하네스·버전·양자화 차이를 명시

# 제외

- 원격 모델 또는 Hermes 설정 변경
- 유료 벤치마크 실행
- 제3자 종합 점수나 블로그를 근거로 한 순위
- `altalt`가 OpenAI 원본 모델을 어떤 방식으로 중계하는지에 대한 미확인 가정

# 출력

- 한국어 요약 보고서
- 출처 원장(JSONL)
- 관찰·불확실성 노트

# 신선도 요구

무료 엔드포인트와 Hermes 큐레이션은 수시로 바뀔 수 있으므로 결론은 조회 시점의 스냅샷이다. 특히 `poolside/laguna-m.1:free`는 OpenRouter가 2026-07-28 종료 예정으로 표시한다.
