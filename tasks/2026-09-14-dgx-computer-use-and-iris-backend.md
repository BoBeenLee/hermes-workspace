# DGX 에 computer_use 를 켜고 kakao_ai_chat 을 Iris 로 이식

- Task type: `feature`
- HIL status: 사용자 요청 (`kakaotalk, cua driver DGX 에도 구성 방안 진행`), 범위는 `kakao_ai_chat` 만 / 읽기+쓰기 완전 동작까지
- Target: `bobeenlee@100.103.30.62` (DGX, 쓰기)
- Completion mode: `review-required`

## 두 작업의 크기가 달랐다

`computer_use` 는 이식이 아니라 **설정**이었고, 카카오톡은 실제 코드였지만 예상보다 **훨씬 작았다**.

## A. computer_use — repo 가 막고 있었다

`cua-driver 0.28.1 aarch64-unknown-linux-gnu` 는 이미 깔려 있었다. 상류 설치기가 넣는다.
막던 것은 이 repo 의 결함 넷:

1. **게이트가 OS 를 봤다.** `[[ $HERMES_REMOTE_OS == macos && $BACKEND == cua-driver ]]` 는 이중
   잠금이고 macos 쪽이 구속력이었다. 백엔드만 보게 고쳤다 — macOS 는 `cua-driver` 이므로 무변화.
2. **`HERMES_COMPUTER_USE_BACKEND=none` 은 상류에 없는 값.** 유효값은 `cua`/`cua-driver`/`""`/`noop`.
   `run_prompt` 가 env 주입 경로를 우회해서 지금까지 안 터졌을 뿐이다.
3. **DISPLAY 가 네 군데 모두 안 갔다.** `remote_bash` 뿐 아니라 `computer-use install`, `verify`,
   그리고 `run_prompt` 까지 — 에이전트가 `cua-driver` 를 **자기가** 띄우므로 디스플레이는 ssh 가
   아니라 에이전트에 닿아야 한다.
4. **`setup-computer-use` 가 기존 항목을 건너뛰었다.** DGX 에 macOS 경로짜리 `cua-driver` 항목이
   `enabled:false` 로 있어서 `hermes mcp test` 가 계속 `/Users/...` 를 쫓았다. 이제 수리한다.

### 진단 실패 둘 (기록용)

- "`list_windows` 가 비었으니 잠금 때문" — 반만 맞았다. 잠금을 풀어도 비어 있었고, 실제 원인은
  **데스크톱에 열린 앱이 하나도 없던 것**이었다. GNOME 서비스 창은 top-level 로 안 센다.
  계산기를 띄우니 즉시 잡혔다.
- `xrdp` 바인드 제한에 `address=` 키를 제안했는데 xrdp 0.9.x 에 **없는 키**다. ini 주석이 정답을
  갖고 있었다: `port=tcp://<addr>:3389`.

### 검증

```
verify-computer-use   mcp ✓ Connected, 툴 60개 / X11 :10 ✓ / AT-SPI ✓
                      check_permissions atspi:true x11:true xsend_event:true
run "list_windows …"  → 열려 있는 창은 1개이고 제목은: 계산기 (gnome-calculator)
```
GRD RDP 는 껐다(3390 소멸, 자격증명이 비어 있어 쓰이지도 않았다). xrdp 3389 는 사용자가 제한.
무인 운영을 위해 GNOME 화면잠금을 껐다 — `lock-enabled false`, `idle-delay 0`.

## B. kakao_ai_chat — Iris 백엔드

`messenger_assistant.py` 와 코드를 공유하지 않고 fail-closed 가드가 없어, 이식 지점이 넷뿐이었다:
읽기 SQL 세 개, 전송 한 개, 발신자 이름, 그리고 `kmsg_chat_id`.

### 값진 함정 하나

**`/query` 는 SELECT 에 `user_id` 와 `v` 가 둘 다 있을 때만 `message`·`attachment` 를 복호화한다.**
`KakaoDecrypt.decrypt(enc, ciphertext, user_id)` 에 그 둘을 넘기기 때문이다. 빠지면 에러도 경고도
없이 base64 를 준다 — **동작하는 코드처럼 보이는 실패**다. `iris_client.require_decryptable()` 이
그런 SELECT 를 거부한다.

이걸 모르고 한참 헤맸다. 같은 행이 쿼리마다 암호문/평문을 오가서 "push 만 복호화된다"고 잘못
결론 내렸고, `/decrypt` 를 파다가 `Illegal base64 character 3f` 를 만났는데 — 이미 복호화된
한글을 base64 로 넘기고 있었기 때문이었다. `/decrypt` 는 결국 필요 없다.

### 나머지 셋

- **`kmsg_chat_id` 소멸.** `chat_id` 가 양쪽 같은 키다. 해석 단계와 `--resolve-rooms` 요구를
  iris 백엔드에서 게이트했다.
- **발신자 이름은 `/ws` 에서만 온다.** `friends` 는 Iris 가 안 붙이는 KakaoTalk2.db 에 있고,
  `chat_rooms.members` 는 숫자 id, `private_meta` 는 *방* 이름이다. push 피드를 캐시로 받고
  미스는 기존 `"알 수 없음"` 으로 떨어진다.
- **self-ssh 불필요.** 리눅스엔 TCC/Keychain 이 없다. (Mac 에서 exit 255 로 플래핑하던 그 구조다.)

### 검증

```
fetch_new_rows / fetch_room_context / fetch_row_by_log_id   전부 평문
send_message(chat_id 만)  → chat_logs 되읽기 성공, speaker=jarvis 로 분류
기존 테스트 55개          전부 통과 (mac 경로 무회귀)
```

## 앞선 판단 정정 셋

1. "카카오톡 슬롯이 22:08 에 밀렸다" — **틀렸다.** 컨테이너는 계속 로그인 상태였고 화면 캡처로
   확인했다. `chat_logs` 가 안 자란 건 그 시각 이후 새 메시지가 없었기 때문이다. QR 재로그인은
   필요 없었다.
2. "전송 경로가 inert 하다" — **틀렸다.** `NotificationReferer` 는 진짜 값이고 `iris.log` 에
   `[jarvis] …` 봇 발신이 `isMine:true` 로 남아 있다. 선행 세션이 이미 뚫어 놨다.
3. "읽기 경로는 push 여야 한다" — **틀렸다.** 위 복호화 규칙 때문이었다.

## 남은 것

- 데몬을 DGX 에 실제 배포 + systemd user unit (`kakao_ai_chat.py` 의 설치 경로가 아직 plist 전용)
- `/ws` 이름 캐시의 라이브 검증 — 현재 방이 self-chat 이라 `sender` 가 자기 자신뿐이었다
- `messenger_assistant.py` 정책 엔진 (가드 13개) — 범위 밖
