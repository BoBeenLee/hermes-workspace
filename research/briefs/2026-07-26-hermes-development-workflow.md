# Hermes Agent 개발 작업 워크플로우 조사 브리프

- 질문: Hermes Agent로 실제 개발 작업을 수행할 때 어떤 워크플로우가 효과적인가?
- 목적: 공개된 1차 자료와 이 저장소의 실제 운영 기록을 결합해 재현 가능한 개발 운영 모델을 제안한다.
- 범위:
  - NousResearch Hermes Agent v0.19.0 / v2026.7.20
  - CLI, persistent goal, subagent delegation, Kanban, git worktree, checkpoints
  - 이 저장소의 원격 macOS Hermes 운영 및 Jarvis Messenger Assistant 개발 사례
- 지역: 글로벌 공개 자료 + 현재 기본 원격 Mac 운영 환경
- 기준 시점: 2026-07-26 KST
- 제외:
  - 모델별 코딩 벤치마크 비교
  - 인증·키·토큰의 실제 값
  - 자동 merge, 자동 배포, 운영 설정 변경의 실행
- 결과 형식: 한국어 심층 보고서, 조사 노트, JSONL 출처 원장
- 신선도 요구: 공식 문서는 설치된 v0.19.0 태그에 고정하고, 현재 상태는 2026-07-26 원격 점검 결과를 사용한다.
- 증거 등급:
  - A: 공식 태그 문서, 소스, merged PR, 로컬 git/task 기록
  - B: 공개 이슈의 사용자 보고
  - C: 조사자의 추론 또는 권고
