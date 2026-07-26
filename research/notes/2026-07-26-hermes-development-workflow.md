# Hermes Agent 개발 워크플로우 조사 노트

## 관찰

- 기본 원격 Mac은 2026-07-26 점검 시 Hermes Agent v0.19.0, cua-driver 0.12.6이며 gateway와 default/content/jarvis/preflight/product 프로필이 실행 중이었다.
- 설치는 공식 v2026.7.20 태그와 일치하지만 upstream보다 119 commits 뒤에 있었다.
- default 프로필 모델은 `openai/gpt-5-nano`, provider는 사용자 정의 endpoint였다. 복잡한 개발 감독에 적합하다는 실증은 이번 조사 범위에 없으므로 repo-specific evaluation 없이 자동 merge 권한을 주면 안 된다.
- 원격 canonical workspace의 `main`은 이미 많은 수정·미추적 파일이 있었다. 이 조사 산출물은 별도 worktree에서 작성해야 한다.
- Antigravity CLI 1.0.10과 artifact root는 존재하지만 `antigravity-check`에서 settings와 MCP config가 missing으로 나왔다. gateway process 목록에 worker process가 보이는 것과 별개로, 현재 경로를 production-ready라고 판정할 수 없다.
- Hermes v0.19.0의 핵심 개발 기능은 worktree, persistent goal completion contract, verification evidence, checkpoint, background subagent, Kanban이다.
- 공식 worktree 문서는 `hermes -w -z`를 예로 들지만, open P2 issue #67458은 one-shot `-z` 경로가 `worktree` 인자를 전달하지 않아 live branch에 commit했다고 보고한다. 설치된 원격 source도 `_run_and_exit_oneshot()`이 `run_oneshot()`에 worktree를 전달하지 않는 형태임을 읽기 전용으로 확인했다. 현재는 interactive `hermes -w` 또는 사람이 먼저 만든 worktree 안에서 one-shot을 실행해야 한다.
- 공식 PR은 verification ledger를 “passive evidence, not guarantees”라고 명시한다. 자동 검증은 증거 수집 장치이며 최종 판단을 대체하지 않는다.
- verify-on-stop은 새 설치에서 기본 off이고 문서-only 변경에는 동작하지 않는다. 프로젝트 표준 검증 명령은 AGENTS.md, goal contract, CI로 명시해야 한다.
- top-level delegation은 v0.19.0에서 background handle과 결과 재전달을 지원한다. 다만 실행 중 프로세스 재시작은 side effect를 증명할 수 없어 attempt가 unknown이 될 수 있고, durable 장기 작업은 Kanban/cron/별도 worker가 더 적합하다.
- subagent는 부모 대화를 모른다. 목표, repo/worktree, 허용 범위, acceptance criteria, 검증 명령, 금지 행동을 모두 context에 넣어야 한다.

## 실제 사례에서 관찰한 패턴

### Jarvis Messenger Assistant

- 최초 구현은 6개 파일, 2,338 lines 추가 규모였다.
- 이후 MCP route refactor는 5개 파일, +367/-284였고, routing/polling hardening은 5개 파일, +805/-81이었다.
- 운영에서 발견된 문제:
  - 현재 발화보다 오래된 날씨 문맥을 우선해 잘못 답함
  - 실제 새 메시지 없이 이전 이벤트를 근거로 send audit가 만들어짐
  - launchd `StartInterval=80`이 실제 약 120초로 coalesce됨
  - tool call이 없거나 두 번인 세션을 성공으로 오판할 가능성
  - MCP 응답 크기 115 KB가 truncation됨
  - Hermes PID 파일 형식 변경으로 parser가 invalid를 반환함
- 반복 해결 패턴:
  - production trace로 정확한 실패 입력과 상태 확인
  - RED 회귀 테스트 작성
  - deterministic controller 경계를 좁힘
  - local unit/compile/OKF/diff checks
  - remote backup 생성
  - live read-only 또는 no-send smoke
  - process/session/cursor 상태 확인
  - `review-required`로 종료

### Hermes upstream verification

- PR #52285는 test/lint/typecheck/build 실행을 session/workspace별 ledger에 기록하고 파일 수정 뒤 기존 evidence를 stale로 만든다.
- PR #55413은 완료 직전 `pre_verify` hook으로 한 번 더 검사·정리하도록 할 수 있지만 built-in verdict를 중복시키지 않는다.
- PR #53552는 검증 loop가 과도하게 개입한 경험 때문에 기본값을 off로 바꾸고 doc-only edits를 제외했다.
- 결론: “항상 자동 검증”보다 “변경 유형별 검증 계약 + evidence ledger + human review”가 현실적이다.

### Delegation 운영 한계

- 2026-04 사용자 이슈 #11508은 동기 `delegate_task`가 coordinator를 막는다고 보고했다.
- v0.19.0 문서와 release는 top-level background delegation, live transcript, durable completion delivery를 제공한다.
- 이 개선은 결과 전달과 관측성을 높였지만, subagent가 부모 맥락을 모르고 실행 side effect가 재시작 뒤 unknown이 될 수 있다는 본질적 한계는 남는다.
- 사용자 이슈 #18591은 강한 모델 하나로 모든 child를 돌릴 때 concurrency/rate-limit 429가 난다고 보고했다. 병렬도는 “가능한 최대”가 아니라 provider quota, prompt size, task independence에 맞춰야 한다.
- open issue #46303은 서로 다른 세션 사이의 memory cross-bleed와 동일 branch/worktree 공유로 실제 clobber 직전까지 간 near-miss를 기록한다.
- open issue #63351은 headless Codex Kanban worker가 source edit는 했지만 git common directory, macOS TMPDIR, disabled network, 승인 부재 때문에 dependency install·stage·commit을 끝내지 못한 사례다.
- open issue #58490은 verify-on-stop이 subagent의 마지막 응답을 검증 문구로 대체해 실제 작업 summary가 parent에 전달되지 않은 사례를 보고한다.
- open issue #59386은 strict OpenAI-compatible custom provider에서 `delegate_task` schema가 HTTP 400을 6 sessions/9회 일으켰다고 보고한다.
- open issue #71453은 v0.19.0에서 `hermes chat -q`가 background child를 띄운 뒤 parent process 종료와 함께 interrupt하는 최신 재현이다.

### 장시간 production 사용

- closed P1 issue #5563은 사용자가 3주간 Claude Opus로 하루 8시간 이상 Hermes를 사용해 DBOS, PostgreSQL, S3, Gmail API 기반 3-actor email pipeline을 개발했고 일관된 성과를 냈다고 보고한다.
- 같은 보고에서 사용자는 12시간 session 중 약 2.6M tokens(69%)를 context replay overhead로 귀속했고, 한 conversation은 약 1.9M tokens 중 89%가 불필요했다고 추정했다.
- state.db corruption 뒤 128 sessions 중 110개만 DB로 복구되었으며 JSON session files는 남아 있었다.
- 700K+ context 이후 실제 local WSL2를 cloud container로 오인한 환경 hallucination도 보고했다.
- maintainer는 closure에서 여러 파일이 silent new sessions가 아니라 growing snapshots/repeated resume signature라며 69%/89%의 원인 해석을 부정했다. state.db auto-repair와 `hermes db repair`, WSL host probe는 후속 변경으로 largely addressed됐다고 설명했다.
- 이 사례는 v0.6.0+의 역사 사례이므로 v0.19.0의 compression, delivery, session 개선 뒤 동일 수치가 재현된다고 볼 수 없다. 확인된 raw observation과 사용자의 원인 추정을 분리해야 한다.

## 반대 증거와 주의

- 공식 release의 성능·기여 수치는 프로젝트 자체 발표이며 독립 벤치마크가 아니다.
- 공개 이슈는 실제 사용자의 경험 보고지만 재현 환경이 완전히 제공되지 않은 경우가 있어 보편화하면 안 된다.
- 2026-07-26 GitHub 상태상 위 여섯 이슈는 open이다. 이 사실은 현재 설치에서 모두 재현된다는 뜻은 아니지만, 자동화 전 smoke test와 fail-closed guard가 필요하다는 강한 신호다.
- Jarvis 사례는 한 조직·한 macOS 환경의 운영 기록이다. 다른 앱이나 Linux/CI 환경에 동일 수치가 적용된다고 볼 수 없다.
- checkpoint는 실제 git history가 아니라 별도 shadow store다. branch/worktree 및 원격 백업을 대체하지 않는다.
- Kanban은 durable coordination에 강하지만 현재 이 원격 보드는 0 tasks이며, 실제 팀 개발 부하 테스트 증거는 이번 조사에 없다.

## 결론을 이끄는 추론

- Hermes의 차별점은 “코드를 더 잘 생성”하는 단일 모델 기능보다, gateway·profiles·memory·skills·cron·delegation으로 개발을 장기 운영할 수 있다는 점이다.
- 따라서 coding assistant처럼 한 번에 큰 지시를 주는 방식보다 supervisor/control-plane으로 쓰는 편이 위험 대비 가치가 높다.
- 최적의 기본 단위는 한 user outcome당 하나의 completion contract, 하나의 branch/worktree, 하나의 verification bundle, 하나의 review handoff다.
