# DGX에 hermes agent 동일 구성 + 카카오톡 제어 가능 여부 조사

- Task type: `analysis-report` (read-only 조사, 원격 변경 없음)
- HIL status: 사용자 직접 요청 (`hermes mac 에 헤르메스 구성처럼 DGX 에 hermes agent 동일 구성 가능한지?` → `Wine 으로 우회로 해도 카카오톡 제어는 못하는거야? 오픈소스나 심층 조사 진행.`)
- Target: `bobeenlee@100.103.30.62` (DGX Spark, read-only), `bobeenlee@bobeen` (read-only)
- Branch/worktree: `.worktrees/kakao-dgx-portability-20260913`
- Completion mode: `done` (report-only. 원격 상태를 바꾸지 않았다)

## Requested Outcome

DGX Spark에 기존 Mac과 동일한 Hermes agent 구성이 가능한지, 그리고 카카오톡 제어까지
동일하게 가능한지 판정한다. 2차 요청으로 Wine 우회 경로와 오픈소스 대안을 전부 조사한다.

## Verdict

| 질문 | 답 |
| --- | --- |
| DGX에 Hermes agent | 가능. headless Linux host. 프로필·runbook이 이미 레포에 있다 |
| DGX에서 카카오톡 제어 | 현재 계정으로는 불가. 막는 것은 소프트웨어가 아니라 **계정 기기 슬롯** |

durable 결론은 [KakaoTalk Control Portability](../knowledge/runbooks/kakaotalk-control-portability.md)로 옮겼다.

## Measured State

DGX (`aitopatom-36a9`, 2026-09-13):

| 항목 | 값 |
| --- | --- |
| OS / arch / kernel | Ubuntu 24.04.4 LTS / aarch64 / `6.17.0-1031-nvidia` |
| GPU / RAM / disk | NVIDIA GB10 / 121GB (110 free) / 3.7T (568G used) |
| `~/.hermes`, `~/.local/bin/hermes` | **둘 다 없음**. 아직 Hermes host가 아니다 |
| desktop | GNOME·Xorg 설치, `graphical.target`. seat0에는 gdm 로그인 화면만, 사용자 GUI 세션 없음 |
| wine / box64 / qemu-x86_64 | 없음. `dpkg --print-foreign-architectures` 비어 있음 |
| docker | 설치·active. `bobeenlee`는 `docker` 그룹 아님, 그룹 자체가 비어 있음 |
| sudo | 비밀번호 필요. NOPASSWD는 `shutdown`/`poweroff` 뿐 |

Mac (`bobeen`): Hermes Agent v0.20.6, install method `git`, `/Applications/KakaoTalk.app` 존재,
`kmsg status` → `Accessibility Permission: ✓ Granted`.

## Evidence Chain

`openhuman-kakaotalk-mac` MCP 서버의 `mcp_server.py`(4508줄)에는 `osascript`,
`AXUIElement`, `CGEvent`, `NSWorkspace` 호출이 **0회**다. 실제 macOS 의존은 vendored
Swift 바이너리 둘에 있다.

- `vendor/kakaocli`: Mach-O arm64, `libsqlcipher` + `Vision.framework` 링크. `~/Library/Containers/com.kakao.KakaoTalkMac/…` DB를 읽고 키는 Keychain `com.kakaocli.credentials`
- `vendor/kmsg`: Mach-O arm64, `AppKit`/`ApplicationServices` 링크, `AXUIElement`/`AXPress`로 KakaoTalk.app 창 조작

## Side Effects

확인 목적으로 실행한 `kmsg status`가 hermes Mac에서 **KakaoTalk.app을 실행시켰다.**
메시지 전송은 없다. `kmsg status`는 read-only probe가 아니다 — runbook에 경고로 기록했다.

## Non-goals

- DGX에 Hermes agent를 실제로 설치하지 않았다
- redroid 컨테이너를 띄우지 않았다 (root 부트스트랩이 사람 손을 요구해 중단)
- 카카오톡 로그인은 어떤 호스트에서도 시도하지 않았다 (기기 슬롯을 소모하므로)

## Verification

```bash
python3 scripts/hermes/validate_okf.py
git diff -- .
```

## Next Action

별도 번호/계정이 확보되면 redroid + Iris PoC. 그 전까지 카카오톡은 default macOS target에 둔다.
DGX는 headless Hermes host 겸 로컬 LLM 백엔드로 붙이는 분리 구성이 남은 선택지다.
