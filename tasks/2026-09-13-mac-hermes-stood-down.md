# Mac hermes 를 내리고 DGX 단독으로 전환 (카카오톡은 포기)

- Task type: `host-cutover`
- HIL status: 사용자 결정 (`mac hermes 는 off 라 생각했고(임시) dgx hermes 로만 구동` → 선택지 셋 중 "카카오 없이 Mac 을 끄다")
- Target: `bobeen` (hermes Mac, 쓰기), `bobeenlee@100.103.30.62` (DGX, 확인만)
- Completion mode: `review-required`

## 왜

[2026-09-13 DGX 이식](2026-09-13-hermes-agent-dgx-port.md) 직후 `메신저 시작` 을 안내했는데,
사용자가 "그건 DGX 에서 도는 게 아니냐" 고 물었다. 아니다 — Mac 프로세스다. 사용자의
원래 그림은 **Mac hermes 는 끄고 DGX 단독**이었고, 그 그림에서는 메신저 비서 자체가
성립하지 않는다.

## 카카오톡이 DGX 로 따라올 수 없는 이유 (실측)

| 막는 것 | 상태 |
| --- | --- |
| 기기 슬롯 | Mac KakaoTalk.app 이 쥐고 있다. DGX 컨테이너 DB 는 22:22 이후 안 자란다 |
| Iris HTTP | 포트 3000 `http=000`. 프로세스(`app_process` pid 1880)는 떠 있지만 안 듣는다. 재기동 + `NotificationReferer` 재발급 필요 (남이 보낸 메시지로 알림이 한 번 떠야 생긴다) |
| 정책 엔진 | `messenger_assistant.py` 의 fail-closed 가드가 macOS 어댑터 근거(`NTUser.directChatId`, `userType`)에 묶여 있다. 전송 계층 교체가 아니라 **규칙 재작성**. [Iris On DGX](../knowledge/runbooks/iris-on-dgx.md) 에 대응표가 있다 |

그래서 사용자가 셋 중 "카카오 없이 Mac 을 끈다" 를 골랐다. 카카오톡 연동은 다음 세션.

## 내린 것

```
hermes gateway stop                      → ✓ Stopped hermes-gateway service
hermes --profile jarvis gateway stop     → ✓ Stopped hermes-gateway-jarvis service  (컷오버 때 이미)
bootout + disable (gui/501):
  ai.hermes.jarvis-messenger-assistant-discord   rc=0
  ai.hermes.jarvis-messenger-assistant-poll      rc=0
  ai.hermes.kakao-ai-chat                        rc=0
  ai.hermes.camofox                              rc=0
  ai.hermes.mlx-qwen                             rc=0       ← 10.0 GB 상주였다
disable only: ai.hermes.gateway-jarvis, ai.hermes.gateway
pkill -f kakao_ai_chat.py                → killed 23525 (고아)
```

최종: `launchctl list | grep hermes` 에 `application.ai.hermes.mac-manager.*` 만 남았다
(전원 스케줄 GUI 앱, 에이전트 아님). hermes 프로세스 0개. 로컬 8080 `http=000`.
KakaoTalk.app 은 건드리지 않았다 — 계정 슬롯을 유지해야 나중에 되돌릴 수 있다.

## 비싼 함정 셋

1. **`launchctl bootout` 은 게이트웨이에 안 통한다.** `launchctl list` 가 라벨을 찍고 있는데도
   `Boot-out failed: 3: No such process` 다. 게이트웨이는 `hermes gateway stop` 으로만 내려간다.
   나머지 에이전트는 bootout 이 되지만 **`gui/<uid>` 에서만** 된다 — `user/<uid>` 로 하면
   똑같은 "No such process" 가 나와서 엉뚱한 곳을 파게 된다. `launchctl print` 로 도메인을
   먼저 확인할 것.
2. **`disable` 까지 해야 한다.** `RunAtLoad` 라 재부팅하면 되살아나고, 되살아난
   `gateway-jarvis` 는 DGX 가 가진 채널에 다시 붙는다 — 이 분리가 막으려던 바로 그 중복이다.
3. **`kakao_ai_chat` 은 고아를 남긴다.** launchd 에 TCC/Keychain 컨텍스트가 없어서 자기를
   로컬 `ssh 127.0.0.1` 로 되감아 실행하는데, launchd 가 감독하는 건 **ssh 쪽**이다.
   bootout 해도 건너편 python 이 계속 돈다. `pkill -f kakao_ai_chat.py` 로 마무리.

## 지금 상태

| | |
| --- | --- |
| DGX `hermes-gateway.service` | active, Discord `Bob Hermes#7289` 연결, 1 platform |
| DGX `run "Reply with exactly: OK"` | OK |
| DGX 로컬 LLM | qwen3.8-27b @ 127.0.0.1:8080 |
| Mac hermes | **전부 down + disabled** |
| 카카오톡 | **어둡다** — Mac 비서도 DGX 경로도 안 돈다 |

## 되돌리려면

```bash
ssh bobeen 'for L in ai.hermes.gateway ai.hermes.gateway-jarvis \
  ai.hermes.jarvis-messenger-assistant-discord ai.hermes.jarvis-messenger-assistant-poll \
  ai.hermes.kakao-ai-chat ai.hermes.camofox ai.hermes.mlx-qwen; do
    launchctl enable "gui/$(id -u)/$L"
    launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/$L.plist 2>/dev/null
  done'
```
**단, `gateway-jarvis` 를 되살리기 전에 DGX 게이트웨이를 먼저 내려야 한다** —
반대로 하면 …3051 에서 둘이 같이 답한다.

## 미검증

- Mac 의 `hermes --profile jarvis -z` 일회성 호출이 150초 안에 안 돌아왔다(두 번). MLX 속도
  때문인지 게이트웨이 부재 때문인지 가리지 못했다. Mac 을 되살릴 때 먼저 확인할 것.
- 재부팅 후 `disable` 이 실제로 유지되는지.
