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

## Addendum: Android Container PoC (2026-09-13, 사용자 승인 후 실행)

- Task type가 `analysis-report`에서 `ops-change`로 올라갔다. Completion mode: `review-required`
- 사용자 요청으로 B안(Android 컨테이너)을 실제로 띄웠다. **카카오톡 로그인은 하지 않았다** — 기기 슬롯 미소모

### 결과

`redroid/redroid:14.0.0_64only-latest` 부팅 성공. 10초, 서비스 49개, 583MB RSS, CPU 0.11%.
`arm64-v8a` 네이티브, SDK 34, 패키지 113개. `input`/`screencap`/`dumpsys activity top`/
`sqlite3`/loopback adbd 전부 동작. 레시피와 함정은
[DGX Android Container](../knowledge/runbooks/dgx-android-container.md)로 옮겼다.

### 사고: DGX 하드 리셋

첫 컨테이너가 19:44:34에 호스트를 재부팅시켰다. `journalctl --list-boots`의 직전 부팅이
systemd 종료 시퀀스 없이 크래시 루프 로그 도중에 끊긴다. 원인은 `--privileged`가 주는
`CAP_SYS_BOOT` + seccomp unconfined 조합이고, Android init이 조기 부팅 실패 시 리부트를
호출한 것이 호스트까지 갔다.

피해 없음: 실패 유닛 0개, ComfyUI user 유닛 정상 복귀, 큐 비어 있었음, Tailscale 정상.

재발 방지: `reboot`/`kexec_*`를 `SCMP_ACT_ERRNO`로 막는 seccomp 프로필을 필수화했다.
`--cap-drop=SYS_BOOT`은 `--privileged` 하에서 무효임을 실측으로 확인했다(`CapEff` 동일).

### 남긴 호스트 상태

| 항목 | 상태 | 되돌리기 |
| --- | --- | --- |
| `binder_linux` 로드 + `/dev/binderfs` 마운트 | 재부팅하면 사라짐 | `rmmod binder_linux` |
| `/dev/binderfs/*` 퍼미션 `0666` | 재부팅하면 사라짐 | 재부팅 |
| `bobeenlee` docker 그룹 | **영구** (root 등가) | `sudo gpasswd -d bobeenlee docker` |
| 컨테이너 `redroid-poc` 실행 중 | 수동 | `docker rm -f redroid-poc` |

### 결론 변화 없음

컨테이너는 된다. 카카오톡은 여전히 **기기 슬롯**에서 막힌다. 별도 번호/계정이 없으면
로그인하는 순간 폰이 밀려난다.

## Addendum 2: 카카오톡 설치·실행 (사용자 승인 후)

**로그인은 하지 않았다.** 기기 슬롯 미소모.

조달: 서드파티 미러를 쓰지 않고 사용자 본인 Galaxy S25 Ultra(SM-S938N, Android 16)에서
ADB로 split 8개를 받았다. 26.7.2, `minSdk=32`, `primaryCpuAbi=arm64-v8a`, 370MB.

설치: `pm install-multiple`은 이미지에 없다(`Unknown command`).
`pm install-create` → `install-write` ×8 → `install-commit` → `Success`.

실행 결과:

| 확인 | 결과 |
| --- | --- |
| 프로세스 | 생존 (pid 1979) |
| 포커스 창 | `com.kakao.talk.activity.authenticator.auth.AuthenticatorActivity` |
| 화면 | 정상 렌더링된 로그인 화면 (스크린샷 확보) |
| 루팅/무결성 차단 | **없음.** `integrity` 매칭 로그 2건은 플랫폼 `FileIntegrity.setUpFsVerity`로 앱 어테스테이션과 무관 |
| `/data/data/com.kakao.talk/databases` | `KakaoTalk.db`, `KakaoTalk2.db` 존재 — Iris가 읽는 그 파일 |
| 뷰 계층 | 124줄 (`dumpsys activity top`) |

무해한 노이즈: `vold: Failed to set project id`(바인드 마운트 `/data`에 project quota 없음),
`VerityUtils: Failed to measure fs-verity`.

### 결론 갱신

기술적 경로는 **로그인 직전까지 전부 검증됐다.** 남은 차단 요인은 하나뿐이다 — 기기 슬롯.
별도 번호/계정이 생기면 그다음은 Iris 이식 작업이고, 없으면 여기가 끝이다.

## Addendum 3: 보조기기 로그인 성공 (사용자 승인 후)

사용자가 "PC 와 유사하게 로그인" 가능성을 물었고, 승인(①) 후 진행했다.

### 게이트는 화면이 아니라 기기 신원이었다

| 시도 | 체크박스 |
| --- | --- |
| 기본 (`sw360dp`, phone) | 없음 |
| `wm size 1600x2560` → `sw800dp xlrg` | 없음 |
| + `ko-KR` 로케일 | 없음 |
| + `ro.build.characteristics=tablet` | 없음 |
| + `ro.product.model/brand/manufacturer` = 태블릿 | **나타남** (기본 체크) + `QR코드 로그인` |

모델·브랜드·제조사를 한 번에 바꿔서 셋 중 무엇이 게이트인지는 분리하지 않았다.
`android.hardware.telephony`는 redroid에 애초에 없어 게이트가 아니다.

### 로그인

`QR코드 로그인` → `SubDeviceQRLoginActivity` → 폰으로 스캔 → `보안 인증번호`(4자리) →
권한 안내 → `MainActivity`. 계정 `이보빈`, 친구 291명 정상 표시.

자격증명은 내가 입력하지 않았다. QR 스캔 방식이라 비밀번호가 내 손을 거치지 않는다.
권한은 알림 허용, **연락처 거부**(불필요), 배터리 최적화 안내는 "다시 보지 않기".

첫 시도는 QR 60초 + 인증번호 60초를 채팅 왕복으로 다 써서 만료됐다. 두 번째에 성공.

### 슬롯 질문의 실측 답

| | 폰(S25 Ultra) | Mac KakaoTalk.app |
| --- | --- | --- |
| 결과 | **유지** | **밀려남** (`osascript` 창 제목 = `Log in`) |

태블릿 보조기기와 PC 클라이언트는 **같은 슬롯**이다. 2차 출처가 맞았다.

Mac 쪽 메신저 비서는 이미 비활성이었다 — `poller.log`는 7월 20일, `poller.error.log`는
8월 2일 이후 갱신 없음. 이번 로그아웃으로 잃은 동작은 없다.

### DB 표면

`/data/data/com.kakao.talk/databases/KakaoTalk.db`(344KB), `KakaoTalk2.db`(1.8MB), 로그인
직후 기록됨. 파일 헤더가 `SQLite format 3` — **파일 레벨은 평문**이고 본문만 필드 단위
암호화다. Iris가 다루는 그 형태. 컨테이너의 `sqlite3` 바이너리는 `Aborted (core dumped)`로
죽는데 이건 이미지의 도구 문제지 암호화가 아니다. 대화 내용은 읽지 않았다.

### 현재 상태

컨테이너가 보조기기로 로그인된 채 떠 있다. Mac을 다시 로그인시키면 컨테이너가 밀려난다.
둘 중 하나만 슬롯을 가질 수 있다.
