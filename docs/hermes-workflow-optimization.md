# Hermes Workflow Optimization

2026-06-22에 Hermes MacBook의 5개 gateway profile을 Hermes Agent v0.17.0 upstream `8a506ed3` 기준으로 업데이트하고, 분석 영상의 context/output/subagent 설정을 운영 프로필별로 나눠 적용했다. 이 변경은 remote config 작업이므로 완료 상태는 `review-required`로 둔다.

## Backup

변경 전 백업:

```text
~/.hermes/config.yaml.bak-20260622-004516
~/.hermes/profiles/product/config.yaml.bak-20260622-004516
~/.hermes/profiles/content/config.yaml.bak-20260622-004516
~/.hermes/profiles/jarvis/config.yaml.bak-20260622-004516
~/.hermes/profiles/preflight/config.yaml.bak-20260622-004516
```

## Common Context Settings

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

## Subagent Settings

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

## Checkpoints

Checkpoint는 파일 변경이 많은 profile 위주로만 켰다.

```text
default: checkpoints.enabled=true
product: checkpoints.enabled=true
jarvis: checkpoints.enabled=true
content: checkpoints.enabled=false
preflight: checkpoints.enabled=false
```

## Quick Commands

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

## Verification

- `hermes update` 완료 후 upstream `8a506ed3` 기준 up to date.
- CuaDriver는 `0.5.8`로 업데이트됐고 Accessibility + Screen Recording 권한이 유지됐다.
- `hermes config check`와 `hermes --profile <profile> config check`가 `default`, `product`, `content`, `jarvis`, `preflight`에서 통과했다.
- 모든 gateway profile을 재시작했고 `bin/hermes-remote status`에서 5개 process가 running 상태임을 확인했다.
- quick command 대상 명령인 `hermes status`, `hermes doctor`, `hermes logs --since 30m`, `hermes logs errors --since 2h`가 실행 가능함을 확인했다.

## Operations Notes

- 전역 persistent YOLO는 켜지 않는다. 필요한 profile의 subagent approval 병목은 `delegation.subagent_auto_approve: true`로만 푼다.
- 실제 5-child LLM delegation 부하 테스트는 Groq TPM 제한으로 인한 `HTTP 413 Request too large` 로그가 있어 실행하지 않았다. 대규모 병렬 작업 전에 provider limit과 prompt 크기를 먼저 확인한다.
- `~/.hermes/.env`, `~/.hermes/auth.json`, provider token, OAuth token은 문서나 git에 기록하지 않는다.
