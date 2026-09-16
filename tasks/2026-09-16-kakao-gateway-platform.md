# 카카오톡을 hermes 게이트웨이 네이티브 채널로 (조사 + `--resume` 실측)

- Task type: `incident-triage` → `ops-change`
- HIL status: 사용자 요청 (`DGX hermes 카톡과 대화 기존 hermes agent와 대화하는 식으로 구성 가능할지?`).
  범위 확정 = **네이티브 게이트웨이 채널 / 모든 방(오픈채팅 포함)**. 오픈채팅 발화 영속화는 승인받음
- Target: `bobeenlee@aitopatom-36a9.tailbb0884.ts.net` (DGX, 읽기 + 배포본 쓰기)
- Completion mode: `review-required`
- 구현 계획 전문은 로컬 플랜 파일. 이 문서는 **실측과 판정**만 남긴다

## 결론

된다. 플러그인 이음매(`ctx.register_platform`)는 실재하고, **지금 Discord 자체가 그 경로로 돈다**
(게이트웨이 로그가 `hermes_plugins.discord_platform.adapter` 를 찍는다). 코어 수정 0이 공식 입장이다
(`gateway/platforms/ADDING_A_PLATFORM.md`). 다만 공짜가 아닌 항목이 셋 있고 전부 사람이 정해야 한다.

## 데몬이 손으로 만든 것 → 게이트웨이 네이티브 슬롯

| 데몬 | 게이트웨이 |
| --- | --- |
| 방 대화록 SQL 재조립 | 세션 자체 (`gateway/session.py:654` `build_session_key` → `state.db.gateway_routing`, `gateway/run_agent_cache.py` 의 방별 `AIAgent` LRU) |
| `OTHERS` 블록 | **`messages.observed` 컬럼** (`hermes_state_common.py:409`). 기록은 `gateway/session_transcript.py:101,338`, 분리는 `gateway/run.py:1186-1259`, 재부착은 `:1286-1305`. 레퍼런스: `plugins/platforms/telegram/adapter.py:5773-5792` |
| `MY_THREAD` / 화자 이름 | `is_shared_multi_user_session` → `[sender name]` 접두 (`gateway/run_inbound.py:1331-1340`), 이름은 `neutralize_untrusted_inline_text` 로 살균 |
| 프롬프트 규칙 블록 | `PlatformEntry.platform_hint` (`gateway/platform_registry.py:79` → `agent/system_prompt.py:384,582`). config `agent.platform_hints.<platform>: {append\|replace}` 로 재배포 없이 조정 |
| `QUOTED` | `reply_to_message_id` / `reply_to_text` / `reply_to_author_id` / `reply_to_is_own_message` |
| 방별 규칙 | `MessageEvent.channel_prompt` — 턴 한정, transcript 에 안 남는다 |
| `jobs/<chat_id>.json` 방 락 | `gateway/turn_lease.py` — resolved session_id 단위 직렬화, 대기 fail-closed(기본 5초) |
| `reap_jobs` / `pending_send` | `gateway/delivery_ledger.py` (`delivery_obligations` 테이블) |
| `post_tool_call` 셸 훅 | `_run_agent_notify_long_running` (`gateway/run_turn.py:3868-3900`, 180초). **`~/.hermes/config.yaml` 의 손붙임 훅 블록이 통째로 사라진다** |
| 12툴셋 하드코딩 문자열 | `config.yaml` 의 `platform_toolsets.kakao` |
| 멘션/방 allowlist | Discord env 세트와 동형 (아래 표) |
| ComfyUI outbox env 해킹 | `cron_deliver_env_var` + `standalone_sender_fn` → `--deliver kakao:<chat_id>`. **프롬프트의 `python3 {send_bin} --send-to` 줄도 같이 사라진다** (방 텍스트에서 도달 가능한 자기호출 프리미티브였다) |

## 실측 1 — before/after (`--resume`)

나와의 채팅 `128426307555607`. T1 의 **최종 답에는 없고 툴 호출 인자에만 있는** 사실을 T2 가 묻는다.
T2 는 툴 재실행을 금지했다.

| | before (턴마다 새 세션) | after (`--resume`) |
| --- | --- | --- |
| T2 답 | **`모름`** | **`/tmp/jarvis_test_20260916.txt` + `오늘도 차분히 한 걸음씩.`** (정확) |
| T2 툴 호출 | 0 | 0 — 재실행 없이 기억에서 |
| T2 소요 | 42초 | **11초** |
| 세션 | 별개 2개, `parent_session_id` NULL | 같은 세션 `20260916_095336_d2dcf7` (mc 6→8, api 3→4) |
| T2 입력 토큰 | 15454 (고정) | ~20.3k (누적 47816 → 68168) |

**끊기는 건 텍스트가 아니라 툴 결과다.** 데몬의 SQL 재조립이 대화록은 이미 이어 주므로 앞 발화를
가리키는 질문은 지금도 통한다. 잃는 건 최종 답에 안 실린 것 — 툴 인자·중간 산출물·작업 상태.
그리고 before 의 오답은 환각이 아니라 정직한 `모름` 이었다. 연속 세션이 고치는 건 정확도가 아니라 **범위**다.

**첫 after 시도는 무효였다**: T1 이 툴을 안 쓰고 "완료"만 답해 기억할 것이 없었다
(`20260916_095106_b073a0`, `tool_call_count=0`). 프리티어 모델이 지시를 건너뛴 것.
**툴 사용을 전제한 측정은 `tool_call_count` 를 먼저 확인하고 판정할 것.**

## 실측 2 — 컨텍스트는 톱니다, 무한이 아니다

| | 값 | 출처 |
| --- | --- | --- |
| 압축 발동 | **131,072** | `context_length 262144 × compression.threshold 0.5` (`agent/context_engine.py:242`) |
| 압축 후 꼬리 | ~10K | `tail_mode` 미설정 = 기본 `lean` = "clamped 2.5%-of-window tail (10K floor / 25K cap)" |
| 보존 | 시스템 프롬프트 + 요약 + 앞 3 + 최근 20 | `protect_first_n` / `protect_last_n` |
| 유휴 압축 | 꺼짐 | `idle_compact_after_seconds: 0` |
| 증가율 (실측) | 턴당 약 5k | T2 호출 입력 20352 = 고정 프롬프트 15k + T1 히스토리 ~5k |

**비싼 쪽은 압축 자체다.** `auxiliary.compression` 이 비어 있어 **메인 모델**
(`nex-agi/nex-n2.5-pro:free`)이 131k 요약을 맡는다. 프리티어 지연 분포를 최악의 크기로 돌리는 것이고
`max_attempts: 3` 이다. 전용 aux 모델 지정이 싸다.

## 실측 3 — Discord 는 연결만 돼 있고 채팅으로 쓰인 적이 없다

```
sessions.source distinct → cli, cron, subagent   (discord 없음)
gateway_routing          → 0행
delivery_obligations     → 0행
journal(전체 부팅)        → message/dispatch/turn 로그 0건
```

게이트웨이는 `discord: connected` 로 22시간째 살아 있지만 **턴을 한 번도 돈 적이 없다.**
즉 "네이티브 채널이면 세션이 이어진다" 는 코드로는 확인되지만 **이 호스트에서 실행된 적이 없다.**
어댑터를 쓰기 전에 일반 채널에서 실제 2~3턴을 만들어 `gateway_routing` 이 차는지 먼저 봐야 한다.

현재 Discord 설정 = `KAKAO_*` 의 템플릿:

| 키 | 값 |
| --- | --- |
| `DISCORD_ALLOWED_CHANNELS` | `1511736678807503051` (일반) — 이 한 채널만 |
| `DISCORD_REQUIRE_MENTION` | `true` |
| `DISCORD_THREAD_REQUIRE_MENTION` | `false` |
| `DISCORD_AUTO_THREAD` | `true` |
| `DISCORD_HISTORY_BACKFILL` | `true` (limit 기본 50) |
| `DISCORD_ALLOWED_USERS` | `1030322338060836874` |
| `DISCORD_IGNORED_CHANNELS` | `1528354202600869918` |

## 결정이 필요한 것 셋

### 1. 신뢰 경계 — `observed` 분리는 **fail-OPEN 이고 텔레그램 소유 문자열에 걸려 있다**

`gateway/run.py:1117` `_TELEGRAM_OBSERVED_CONTEXT_PROMPT_MARKER = "observed Telegram group context"`,
판정은 `:1122-1127` 이 `channel_prompt` 에 그 부분문자열이 있는지만 본다.
**마커가 없으면 `observed=True` 행이 `:1220` 의 `elif content:` 로 떨어져 평범한 user 턴으로 재생된다.**
로그도 테스트도 없다. 낯선 사람의 한 줄이 조용히 지시가 된다.

- B1 카톡 `channel_prompt` 에 리터럴을 박는다 (코어 수정 0, 단 남의 플랫폼 매직 스트링)
- B2 상류 일반화: `PlatformEntry.observed_context_mode` + `run.py:1118-1119` 헤더 파라미터화 (~30줄). **권장 목표**
- B3 어댑터가 마커 부재 시 `observed` 행 쓰기를 거부 (B1/B2 와 무관하게 같이)

**`channel_context` 를 연속 세션에 쓰면 안 된다.** `gateway/run_inbound.py:1341-1343` 이
`message_text` 에 접두하고 그게 `run_turn.py:1339` 에서 **영속화**된다. Discord/Slack 은 새 스레드
1회성이라 무해하지만 방별 연속 세션에서는 매 턴 user 행에 이전 방 잡담이 신뢰 표시 없이 쌓인다.
**이번 `--resume` 패치가 같은 현상을 실측으로 보여줬다** — 재개된 세션 안에 데몬 `PROMPT_TEMPLATE`
전문이 턴마다 통째로 다시 들어갔다 (`messages` 940·942 둘 다 전문). 세션 히스토리와 SQL 재조립이
같은 대화록을 이중으로 나른다.

### 2. 턴 벽시계 캡이 게이트웨이에 **없다**

- `agent.gateway_timeout`(1800) — `run_turn.py:3181-3186`: *"**Inactivity** timeout … **not wall-clock**"*. 툴을 계속 부르는 턴은 안 걸린다
- `agent.run_budget_seconds` — 80% 권고문 주입뿐 (`agent/conversation_loop.py:119-145`). 안 자른다
- `agent.max_turns` — 반복 횟수 캡. 현재 500
- `state.db` 의 `session_turn_leases` — **컨텍스트 압축 리스**다. 턴 길이와 무관
- `gateway/turn_lease.py` — 뮤텍스. 5초는 대기자 예산이지 보유자 상한이 아니다

실제로 죽이는 건 `_abandon_timed_out_gateway_turn`(`gateway/run.py:2615-2643`) 하나이고 호출부가
두 inactivity 경로와 `/stop` 뿐이다. → 수용하거나, `run_turn.py:3229-3240` 옆에 벽시계 타이머를
하나 더 걸어 같은 리퍼를 부른다(약 10줄, `timeout_fired`/`cleanup_lock` 재사용).

곁가지: 인프로세스에서는 `kill_process_group` 이 `_reap_gateway_turn_processes` 로 약화된다 —
`tools/process_registry.py` 에 기록된 것만 거둔다. 등록 밖에서 샌 MCP 서버·브라우저는 살아남고,
DGX 에서는 그게 GPU 를 쥔다.

### 3. 프라이버시 자세가 뒤집힌다 (승인됨)

데몬 docstring 이 *"Raw KakaoTalk text is not written to state.json"* 을 약속한다. 게이트웨이로 가면
오픈채팅 발화가 `state.db.messages` 에 영속되고 `messages_fts` 로 색인돼 `session_search` 로 검색된다.
`PlatformEntry.pii_safe` 는 세션 *설명* 만 가리지 내용은 아니다. **2026-09-16 사용자 승인.**

## 함정 (구현 전에 알아야 하는 것)

- **`/ws` 는 40~45초마다 끊기지 않는다 (정정).** 2026-09-16 재측정: 80초 연결, close 0회,
  5초 idle timeout 16연속. 옛 증상은 `recv timeout` 을 끊김으로 읽던 버그였다.
  `async for raw in ws:` 형태면 구조적으로 재발하지 않는다
- **`/ws` 를 두 리더가 같이 읽어도 안전하다** (브로드캐스트, 큐 아님). 데몬을 끄지 않고 인바운드만
  검증할 수 있다. 막아야 하는 건 이중 *응답* 뿐이다
- **`PlatformEntry` 는 26필드다.** `supports_threads` / `markdown_dialect` 는 **없다** —
  `gateway/relay/descriptor.py:30-31` 의 릴레이 전용 필드다. 마크다운은 `format_message()` 오버라이드
  + `supports_code_blocks=False` + `platform_hint` 로 한다
- **템플릿은 `plugins/platforms/simplex/`** (로컬 데몬으로의 WS 클라이언트). LINE 은 webhook 서버라
  모양이 다르다. 등록 블록과 `strip_markdown_preserving_urls` 만 LINE 에서 가져온다
- **봇이 운영자 본인 계정으로 발신한다** → 자기 메시지 필터를 `user_id` 로 못 만든다.
  `row_is_bot()`(prefix + author_id) 를 그대로 포팅할 것. 틀리면 무한 응답 루프다
- **`group_sessions_per_user` split-brain**: 어댑터(`gateway/platforms/base.py:2293-2298`)는
  `config.extra` 를, 실제 라우팅(`gateway/session_recovery.py:90-99`, `run_inbound.py:1327-1330`)은
  전역 `GatewayConfig` 를 읽는다. 한쪽만 바꾸면 어댑터는 키 A 를 잠그고 에이전트는 키 B 로 라우팅한다.
  건드리지 않으면 `run_adapters.py:1495` 가 전역을 extra 에 setdefault 해서 양쪽이 일치한다.
  현 트리거가 author-scoped 라 1단계에선 끌 필요 자체가 없다
- **config 중첩 함정**: `gateway: { kakao: {...} }` 로 쓰면 조용히 버려진다 — 그 경로가 `Platform(k)` 를
  `discover_plugins()` **전에** 호출한다. **최상위 `kakao:` 블록**을 쓸 것
- `busy_input_mode` 기본값이 `interrupt` 라 두 번째 멘션이 첫 답을 죽인다. 데몬의 `TURN_BUSY_NOTE`
  계약과 정반대 — `queue` 로 둘 것
- `gateway/slash_access.py` 의 `allow_admin_from` 을 **dm·group 양쪽 스코프에** 설정하지 않으면
  게이팅이 꺼진 상태라 오픈채팅의 낯선 사람이 `/stop`·`/model`·`/new` 를 쓴다
- `display.platforms.<plugin>` 이 플러그인 키를 받는지 **미확인**. 기본 폴백이 `tool_progress: "all"` 이라
  첫 턴부터 방이 도배될 수 있다 — Stage 1 에서 먼저 확인

## 배포본에 들어간 변경 (레포보다 앞선다)

`~/.hermes/kakao-ai-chat/kakao_ai_chat.py` 에만 적용. 백업:
`kakao_ai_chat.py.bak-20260916-094954`(--resume 전), `...-20260916-103132`(TTL 전).

1. `SESSIONS_DIR` 상수 + `SESSION_TTL_SECONDS = 6*3600`
2. `session_path` / `load_session_id` / `save_session_id` / `reset_sessions`
3. `run_hermes` 가 저장된 id 로 `--resume` 를 붙인다
4. `finally` 가 `--usage-file` 의 `session_id` 를 **지우기 전에** 회수한다 (원래는 읽지도 않고 삭제)
5. `--resume` 실패 시 저장된 id 폐기 (stale/압축 대상 자가 치유)
6. TTL 초과 세션은 `load_session_id` 가 폐기, Discord 제어 채널에 `세션 초기화` 명령 추가

자가 검증: `tests/check_kakao_sessions.py` (배포본 대상, DGX 에서 실행).

⚠️ **레포본이 배포본보다 뒤져 있다** — `scripts/hermes/kakao_ai_chat.py` 2472줄 vs 배포본 2706줄.
위 변경을 레포에 반영하려면 **먼저 234줄치 드리프트를 동기화**해야 한다. 별도 작업으로 남긴다.

## 검증 명령

```bash
# 게이트웨이 세션이 실제로 이어지는가 (Discord 로 2~3턴 먼저 만들 것)
sqlite3 ~/.hermes/state.db "select scope, session_key from gateway_routing;"
sqlite3 ~/.hermes/state.db "select id, source, session_key, chat_id, chat_type from sessions where session_key is not null order by started_at desc limit 5;"

# --resume 이 붙었는지 (새 세션 행이 안 생기고 mc 가 늘면 붙은 것)
sqlite3 ~/.hermes/state.db "select id, message_count, api_call_count, tool_call_count, input_tokens from sessions order by started_at desc limit 3;"

# TTL/reset 자가 검증
ssh <dgx> '~/.hermes/hermes-agent/venv/bin/python /path/to/check_kakao_sessions.py'
```
