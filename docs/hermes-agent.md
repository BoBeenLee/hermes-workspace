# Hermes Agent 운영 노트

이 문서는 이슈 #36의 Hermes MacBook 원격 구축 절차를 정리한다. 대상 agent는 NousResearch의 `hermes-agent`이며, 설치 경로는 공식 가이드의 기본 per-user layout을 따른다.

## 대상

| 항목 | 값 |
|------|----|
| Hermes MacBook SSH | `bobeenlee@192.168.0.8` |
| SSH key | `~/.ssh/id_ed25519_bobeenlee_nopass` |
| 공식 code path | `~/.hermes/hermes-agent` |
| 공식 data/config/session/log path | `~/.hermes` |
| 공식 command path | `~/.local/bin/hermes` |

현재 설치 상태:

- `scripts/hermes/install.sh`로 공식 path 설치 완료.
- `scripts/hermes/doctor.sh`에서 `~/.hermes/hermes-agent`, `~/.local/bin/hermes`, managed `uv`, managed Node/npm 확인 완료.
- 모델 기본값은 `model.provider=openrouter`, `model.default=openrouter/free`로 설정했다.
- `OPENROUTER_API_KEY`는 Hermes MacBook의 `~/.hermes/.env`에 구성했고, `hermes --provider openrouter --model openrouter/free -z ...` smoke test가 통과했다.
- gateway는 user-level launchd로 설치·시작했다. `hermes gateway status`에서 `ai.hermes.gateway`가 loaded 상태로 확인된다.
- Telegram/Discord 같은 messaging provider는 아직 구성하지 않았다.

기본 접속:

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass -o IdentitiesOnly=yes bobeenlee@192.168.0.8
```

## 진단

Control MacBook에서 실행한다.

```bash
scripts/hermes/doctor.sh
```

확인 항목:

- SSH key가 passphrase prompt 없이 public key를 읽을 수 있는지
- Hermes MacBook에 SSH 접속 가능한지
- 원격 macOS 버전과 `git`, `python3`, `node`, `npm`, `launchctl`, `curl` 존재 여부
- 공식 installer가 관리하는 `~/.hermes/bin/uv`, `~/.hermes/node/bin/node`, `~/.hermes/node/bin/npm` 존재 여부
- `~/.hermes/hermes-agent`, `~/.local/bin/hermes`, `~/.hermes/logs/gateway.log`, launchd plist 존재 여부
- Hermes가 설치된 경우 `hermes doctor`와 `hermes gateway status`

IP나 key가 바뀌면 옵션으로 덮어쓴다.

```bash
scripts/hermes/doctor.sh --host BoBeenui-MacBookPro.local
scripts/hermes/doctor.sh --host 192.168.0.8 --key ~/.ssh/id_ed25519_bobeenlee_nopass
```

## 설치

먼저 dry run으로 원격에서 실행될 작업을 확인한다.

```bash
scripts/hermes/install.sh --dry-run
```

실제 설치:

```bash
scripts/hermes/install.sh
```

기본 설치는 공식 installer를 사용하되 setup wizard와 browser tooling을 건너뛴다.

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive
```

browser tooling이 필요하다고 확인된 뒤에만 명시적으로 설치한다.

```bash
scripts/hermes/install.sh --with-browser
```

설치 후 foreground 검증:

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass -o IdentitiesOnly=yes bobeenlee@192.168.0.8 '~/.local/bin/hermes doctor'
```

비대화형 SSH에서는 shell profile이 로드되지 않을 수 있다. Hermes의 관리 Node runtime까지 포함해 진단하려면 아래처럼 PATH를 명시한다.

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass -o IdentitiesOnly=yes bobeenlee@192.168.0.8 'PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$PATH" hermes doctor'
```

## Setup

모델 provider는 OpenRouter로 설정했고, 초기 모델은 OpenRouter의 무료 라우터인 `openrouter/free`로 둔다. OpenRouter API key는 Hermes MacBook의 `~/.hermes/.env`에만 저장한다. Nous Portal OAuth, Telegram/Discord 같은 messaging provider 설정은 자동화하지 않는다. 필요한 secret과 OAuth 입력은 Hermes MacBook에서 사람이 직접 수행한다.

```bash
~/.local/bin/hermes config set OPENROUTER_API_KEY sk-or-...
~/.local/bin/hermes doctor
```

smoke test:

```bash
~/.local/bin/hermes --provider openrouter --model openrouter/free -z "Reply with exactly: OK"
```

검증 결과: `OK`

대화형으로 다시 설정하려면:

```bash
~/.local/bin/hermes model
```

messaging provider를 구성하려면:

```bash
~/.local/bin/hermes gateway setup
```

보안 가드:

- messaging allowlist를 설정한다.
- `GATEWAY_ALLOW_ALL_USERS=true`는 사용하지 않는다.
- API key, OAuth token, provider secret, private key는 repo와 이 문서에 기록하지 않는다.

## Workflow Optimization Snapshot

2026-06-22에 Hermes MacBook의 5개 gateway profile을 Hermes Agent v0.17.0 upstream `8a506ed3` 기준으로 업데이트하고, 분석 영상의 context/output/subagent 설정을 운영 프로필별로 나눠 적용했다. 이 변경은 remote config 작업이므로 완료 상태는 `review-required`로 둔다.

변경 전 백업:

```text
~/.hermes/config.yaml.bak-20260622-004516
~/.hermes/profiles/product/config.yaml.bak-20260622-004516
~/.hermes/profiles/content/config.yaml.bak-20260622-004516
~/.hermes/profiles/jarvis/config.yaml.bak-20260622-004516
~/.hermes/profiles/preflight/config.yaml.bak-20260622-004516
```

전체 profile 공통 context/output 설정:

```yaml
tool_output:
  max_bytes: 200000
  max_lines: 5000
  max_line_length: 10000
file_read_max_chars: 500000
compression:
  enabled: true
  threshold: 0.75
  target_ratio: 0.20
```

`product`, `content`, `jarvis`는 cloud provider 기반 profile이므로 subagent 병렬 처리와 nested orchestration을 켰다. 품질 안정성을 위해 subagent reasoning effort는 `medium`으로 통일했고, background 폭주를 막기 위해 async child 한도는 `3`으로 유지한다.

```yaml
delegation:
  max_concurrent_children: 5
  max_async_children: 3
  max_spawn_depth: 2
  orchestrator_enabled: true
  subagent_auto_approve: true
  reasoning_effort: medium
```

`preflight`는 local MLX Qwen provider를 쓰는 검증용 profile이다. local LLM 부하를 키우지 않기 위해 병렬도와 spawn depth는 기본 수준으로 유지하되, subagent approval prompt 병목만 제거했다.

```yaml
delegation:
  max_concurrent_children: 3
  max_async_children: 3
  max_spawn_depth: 1
  orchestrator_enabled: true
  subagent_auto_approve: true
```

Checkpoint는 파일 변경이 많은 profile 위주로만 켰다.

```text
default: checkpoints.enabled=true
product: checkpoints.enabled=true
jarvis: checkpoints.enabled=true
content: checkpoints.enabled=false
preflight: checkpoints.enabled=false
```

Quick commands는 main/default profile에만 둔다. named profile에 중복 등록하면 gateway 운영 명령이 어느 profile에서 실행되는지 혼동될 수 있기 때문이다.

```yaml
quick_commands:
  hstatus:
    type: exec
    command: hermes status
  hdoctor:
    type: exec
    command: hermes doctor
  hlogs:
    type: exec
    command: hermes logs --since 30m
  herrors:
    type: exec
    command: hermes logs errors --since 2h
  hrestart:
    type: alias
    target: /gateway restart
```

검증 결과:

- `hermes update` 완료 후 upstream `8a506ed3` 기준 up to date.
- CuaDriver는 `0.5.8`로 업데이트됐고 Accessibility + Screen Recording 권한이 유지됐다.
- `hermes config check`와 `hermes --profile <profile> config check`가 `default`, `product`, `content`, `jarvis`, `preflight`에서 통과했다.
- 모든 gateway profile을 재시작했고 `bin/hermes-remote status`에서 5개 process가 running 상태임을 확인했다.
- quick command 대상 명령인 `hermes status`, `hermes doctor`, `hermes logs --since 30m`, `hermes logs errors --since 2h`가 실행 가능함을 확인했다.

운영 주의:

- 전역 persistent YOLO는 켜지 않는다. 필요한 profile의 subagent approval 병목은 `delegation.subagent_auto_approve: true`로만 푼다.
- 실제 5-child LLM delegation 부하 테스트는 Groq TPM 제한으로 인한 `HTTP 413 Request too large` 로그가 있어 실행하지 않았다. 대규모 병렬 작업 전에 provider limit과 prompt 크기를 먼저 확인한다.
- `~/.hermes/.env`, `~/.hermes/auth.json`, provider token, OAuth token은 문서나 git에 기록하지 않는다.

## Gateway

CLI-first gateway 운영을 위해 Hermes 공식 명령으로 user-level launchd agent를 설치·시작했다. Telegram/Discord 같은 messaging provider는 아직 구성하지 않았다.

```bash
~/.local/bin/hermes gateway install
~/.local/bin/hermes gateway start
~/.local/bin/hermes gateway status
tail -f ~/.hermes/logs/gateway.log
```

macOS launchd plist는 공식 기본값 기준으로 아래에 생성된다.

```text
~/Library/LaunchAgents/ai.hermes.gateway.plist
```

검증 결과:

- `~/.local/bin/hermes gateway status`: service loaded
- `~/.hermes/logs/gateway.log`: present
- `~/.hermes/logs/gateway.error.log`: fatal error 없음

중지와 rollback:

```bash
~/.local/bin/hermes gateway stop
launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway.plist
```

접근 회수는 Hermes MacBook의 `~/.ssh/authorized_keys`에서 `codex-to-bobeenlee-nopass` public key 줄을 제거한다.
