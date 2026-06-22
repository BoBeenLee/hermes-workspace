# Hermes Agent Multi-Host Bootstrap

이 문서는 현재 Hermes MacBook 구성을 다른 macOS 또는 Linux/DGX Spark 호스트로 이식할 때 따르는 runbook이다. 목표는 설치 파일을 통째로 복제하는 것이 아니라, target profile을 추가하고 새 호스트에 per-user Hermes Agent를 재구성하는 것이다.

## Target Profile

호스트별 값은 `config/targets/<target>.env`에 둔다.

```bash
cp config/targets/macos-example.env config/targets/<mac-target>.env
cp config/targets/linux-example.env config/targets/<linux-target>.env
cp config/targets/dgx-spark-example.env config/targets/<dgx-target>.env
```

필수 값:

```env
HERMES_REMOTE_HOST=<ssh-alias-or-host>
HERMES_REMOTE_USER=<remote-user>
HERMES_REMOTE_HOME=/Users/<user>      # macOS
HERMES_REMOTE_HOME=/home/<user>       # Linux
HERMES_REMOTE_OS=macos|linux
HERMES_SERVICE_MANAGER=launchd|systemd
HERMES_COMPUTER_USE_BACKEND=cua-driver|none
HERMES_BIN=<home>/.local/bin/hermes
HERMES_CONFIG=<home>/.hermes/config.yaml
HERMES_REMOTE_WORKSPACE=<home>/Workspaces/hermes-workspace
```

운영 명령은 profile을 명시해서 실행한다.

```bash
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote check-ssh
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote status
```

## Bootstrap Order

1. SSH alias, key, remote user, home directory를 확인한다.
2. `scripts/hermes/install.sh --target-profile config/targets/<target>.env --dry-run`으로 변경 내용을 먼저 확인한다.
3. `scripts/hermes/install.sh --target-profile config/targets/<target>.env`로 공식 installer를 실행한다.
4. `scripts/hermes/doctor.sh --target-profile config/targets/<target>.env`로 설치 경로, managed runtime, gateway 상태를 확인한다.
5. 새 호스트에서 사람이 `hermes model`, `hermes auth`, `hermes gateway setup` 등으로 provider/auth/messaging을 재설정한다.
6. `HERMES_TARGET=... bin/hermes-remote setup-kanban`으로 Kanban dispatcher를 구성한다.
7. macOS target이면 `setup-computer-use`, `grant-computer-use`, `verify-computer-use` 순서로 CuaDriver를 확인한다.
8. `gateway-restart`와 `status`로 상시 gateway 상태를 확인한다.

## Secret And Auth Policy

기존 Mac의 다음 파일과 값은 복사하지 않는다.

- `~/.hermes/.env`
- `~/.hermes/auth.json`
- provider API keys
- OAuth tokens
- Discord tokens
- SSH private keys
- raw config output that includes secrets

기존 config는 구조와 profile 이름만 참고한다. API key와 OAuth는 새 호스트에서 사람이 다시 입력한다. 필요한 경우 secret이 없는 설정 diff만 문서화한다.

## macOS Target

macOS target은 desktop control까지 포함한다.

```env
HERMES_REMOTE_OS=macos
HERMES_SERVICE_MANAGER=launchd
HERMES_COMPUTER_USE_BACKEND=cua-driver
```

검증:

```bash
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote check-ssh
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote status
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote verify-computer-use
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote gateway-restart
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote status
```

`grant-computer-use`는 권한 창을 열 수 있지만, Accessibility와 Screen Recording 승인은 사용자가 System Settings에서 직접 완료해야 할 수 있다.

## Linux / DGX Target

Linux와 DGX Spark target은 headless Hermes host로 본다.

```env
HERMES_REMOTE_OS=linux
HERMES_SERVICE_MANAGER=systemd
HERMES_COMPUTER_USE_BACKEND=none
```

검증:

```bash
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote check-ssh
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote status
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote run "Reply with exactly: OK"
```

`setup-computer-use`, `grant-computer-use`, `verify-computer-use`는 Linux target에서 unsupported 메시지로 종료되어야 한다.

로컬/self-hosted LLM provider를 붙일 때는 모델 서버를 loopback에 묶고 SSH tunnel을 우선 사용한다.

```bash
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote check-llm-endpoint http://127.0.0.1:8000/v1
```

## Completion Mode

다음 작업은 완료 보고를 `review-required`로 둔다.

- remote `~/.hermes/config.yaml` 변경
- gateway restart 또는 launchd/systemd service 변경
- CuaDriver permission grant
- key/auth/provider/messaging 변경
- 새 호스트 bootstrap 완료

코드나 문서만 바꾼 경우에도 ops behavior가 바뀌면 merge 전 human review가 필요하다.
