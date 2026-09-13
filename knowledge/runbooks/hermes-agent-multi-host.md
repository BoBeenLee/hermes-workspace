---
type: Runbook
title: Hermes Agent Multi-Host Bootstrap
description: Bootstrap runbook for macOS and Linux Hermes host profiles.
resource: repo://hermes-workspace/knowledge/runbooks/hermes-agent-multi-host.md
tags: [hermes, multi-host, bootstrap]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/hermes-agent-multi-host.md
---

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
HERMES_TARGET=config/targets/<target>.env bin/hermes-remote check-llm-endpoint http://127.0.0.1:8080/v1
```

## DGX Spark: Verified Bootstrap (2026-09-13)

`config/targets/dgx-spark.env` is the live profile. The DGX now runs Hermes Agent
v0.21.2 as a headless Linux host beside the Mac. Six things cost time; none of them
are in the generic order above.

**The target host value must carry the user.** `bin/hermes-remote` calls
`ssh "$HERMES_REMOTE_HOST"` and never prepends `HERMES_REMOTE_USER`, while
`install.sh` / `doctor.sh` build `"${USER}@${HOST}"` only when the host has no `@`
already. A bare IP therefore installs fine and then fails every `hermes-remote`
subcommand with `Permission denied`. There is no `~/.ssh/config` alias for this box
(`bobeen` is the Mac), so the profile carries `bobeenlee@100.103.30.62` — the
Tailscale address, since the mDNS name is the least reliable of the three routes.

**`~/.local/bin` is on the login PATH only.** A non-interactive
`ssh host 'command -v uv'` reports not-found. `install.sh` and `doctor.sh` export a
correct PATH inside their own heredocs, but `bin/hermes-remote` injects
`HERMES_REMOTE_PATH` into all 40 subcommands and its default was missing
`~/.hermes/node/bin`, where the managed Node lives. That default now includes it.

**Interactive commands eat the heredoc.** `hermes model` refuses a non-TTY outright
(`requires an interactive terminal`). Worse, `hermes config migrate` prompts and will
silently swallow the *rest of an `ssh 'bash -s' <<EOF` script* as its answer. Redirect
stdin (`</dev/null`) on every remote `hermes` call that might prompt.

**`hermes config set` takes JSON, and bare `model` is redirected.**
`hermes config set model '<json>'` is rewritten to `model.default` and stores the JSON
as a literal string. Set `model.provider`, `model.default`, `model.base_url`,
`model.api_mode`, `model.context_length` one at a time. Nested keys such as
`providers`, `fallback_providers`, `custom_providers`, `mcp_servers` do accept a JSON
argument and land as proper YAML. Prefer this over editing `config.yaml` by hand: the
v0.21.2 default config is 2138 heavily-commented lines and a YAML round-trip strips
every comment.

**Do not clone the Mac's `config.yaml`.** The Mac is on v0.20.6 (`_config_version` 39,
699 lines); the DGX shipped v0.21.2 with sections the older file has never heard of
(`database`, `runtime`, `prompt_caching`, `telemetry`, …). Port the identity-bearing
sections with `hermes config set` and let `hermes config migrate` bring the version
forward (0 → 44 here).

**The gateway is a systemd *user* unit.** `hermes gateway install` writes
`~/.config/systemd/user/hermes-gateway.service` (a named profile would get
`hermes-gateway-<profile>.service`), enables it via `default.target.wants`, and reports
lingering itself. No sudo anywhere — which matters, because `sudo` on this box requires
a password and there is no TTY over a plain SSH command. `doctor.sh` now prints
`systemd_gateway_active`, `systemd_gateway_enabled`, and `systemd_linger` under the same
guard style as the launchd plist check.

**Local LLM.** `llama-local.service` (systemd --user) serves llama.cpp on
`127.0.0.1:8080/v1`; the model is chosen by `~/.local/bin/dgx-ai-control`. The older
`dgx-spark-example.env` pointed at vLLM on 8000 — nothing has ever listened there.
The served model id is the **full GGUF path**, not a short name. It is a reasoning
model: a bare `/v1/chat/completions` probe with a small `max_tokens` returns an empty
`content` because the budget is spent inside `reasoning_content`. Give it room before
concluding the server is broken.

## Profile Asymmetry: dgx-jarvis And mac-jarvis

The two hosts hold the same Discord identity in differently-shaped profiles, on
purpose.

| | Host | Profile location | Gateway | Alias |
| --- | --- | --- | --- | --- |
| dgx-jarvis | DGX | `~/.hermes/` (**default profile**) | `hermes-gateway.service` | `~/.local/bin/dgx-jarvis` |
| mac-jarvis | Mac | `~/.hermes/profiles/mac-jarvis/` | not installed | `mac-jarvis` |
| jarvis | Mac | `~/.hermes/profiles/jarvis/` | stopped | `jarvis` |

The DGX uses the **default** profile rather than a named one because
`bin/hermes-remote` only passes `--profile` for the Hallmark commands; `status`, `run`,
`gateway-restart`, and `setup-kanban` all address the default profile, and
`HERMES_CONFIG` defaults to `~/.hermes/config.yaml`. A named profile on the DGX would
leave those 40 subcommands talking to an empty default. The alias wrapper supplies the
name instead.

`mac-jarvis` is the restored `product` profile (deleted 2026-08-29, recovered from
`~/.hermes/backups/pre-update-2026-08-29-163521.zip`). Two things to know about it: its
Discord channel variables are deliberately **empty** so its bot can never answer
alongside the DGX on the same channel, and the backup zip excluded every `.git`
directory, so `skill-sources/hallmark` has files but no git metadata —
`check-hallmark-update` reports that until `setup-hallmark` re-creates the checkout.

`bin/hermes-remote`'s Hallmark commands used to hardcode the `product` profile and had
been broken since that profile was deleted. They now read `HERMES_HALLMARK_PROFILE`,
defaulting to `mac-jarvis`.

## Completion Mode

다음 작업은 완료 보고를 `review-required`로 둔다.

- remote `~/.hermes/config.yaml` 변경
- gateway restart 또는 launchd/systemd service 변경
- CuaDriver permission grant
- key/auth/provider/messaging 변경
- 새 호스트 bootstrap 완료

코드나 문서만 바꾼 경우에도 ops behavior가 바뀌면 merge 전 human review가 필요하다.
