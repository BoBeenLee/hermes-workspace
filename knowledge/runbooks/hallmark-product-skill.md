---
type: Runbook
title: Hallmark Product Profile Skill
description: Install, verify, update, and roll back the pinned Hallmark design skill on the remote Hermes product profile.
resource: repo://hermes-workspace/knowledge/runbooks/hallmark-product-skill.md
tags: [hermes, hallmark, skills, product, macos]
timestamp: 2026-07-26T17:27:23+09:00
---

# Hallmark Product Profile Skill

이 runbook은 기본 원격 Mac의 Hermes `product` 프로필에
[Nutlope/hallmark](https://github.com/Nutlope/hallmark) 디자인 스킬을
구성하고 운영하는 절차다. Hallmark는 `product`에만 노출하며 default,
`content`, `jarvis`, `preflight` 프로필에는 설치하지 않는다.

## 설치 구조

Hermes의 표준 스킬 디렉터리 구조와 `skills.external_dirs`를 사용한다.

```text
~/.hermes/profiles/product/
├── config.yaml
└── skill-sources/
    └── hallmark/
        └── skills/
            └── hallmark/
                ├── SKILL.md
                └── references/
```

`config/skills/hallmark.lock`이 저장소 URL, 버전, commit, skill tree hash,
파일 수의 단일 source of truth다. 원격 checkout은 detached HEAD와 sparse
checkout으로 정확히 그 commit을 사용한다.

Hallmark 1.1.0은 `references/components/`, `references/themes/`처럼
디렉터리를 가리키는 링크를 포함한다. 현재 원격 Hermes v0.19.0의
`hermes skills install`은 개별 support file만 bundle로 가져오므로 이
skill을 완전하게 설치하지 못한다. 전체 `skills/hallmark/` tree를
외부 skill source로 제공해야 한다.

## 승인 게이트

최초 설치와 모든 update는 다음 Approval Summary를 사용한다.

- goal: lock에 고정된 Hallmark를 `product` 프로필에 적용
- scope: product config, product Hallmark checkout, product gateway
- non-goals: 다른 프로필, Hermes update, 인증/키, 자동 update
- verification: integrity, profile isolation, gateway, read-only audit smoke
- completion mode: `review-required`

명시적 승인 후에만 `setup-hallmark`를 실행한다.

## 최초 설치

Control workspace에서 사전 상태를 확인한다.

```bash
bin/hermes-remote check-ssh
bin/hermes-remote status
bin/hermes-remote check-hallmark-update
```

고정 commit을 적용한다.

```bash
bin/hermes-remote setup-hallmark
bin/hermes-remote verify-hallmark
```

`setup-hallmark`는 다음 순서로 동작한다.

1. 기존 checkout이 dirty하거나 origin이 다르면 중단한다.
2. 새 임시 checkout에서 commit, version, tree hash, 파일 수와 mode를 검증한다.
3. product `config.yaml`을 타임스탬프 backup한다.
4. 이전 checkout이 있으면 타임스탬프 backup으로 이동한다.
5. `skills.external_dirs`에 `skill-sources/hallmark/skills`를 한 번만 추가한다.
6. 변경이 있을 때만 product gateway를 재시작한다.
7. 실패하면 config와 이전 checkout을 복구하고 product gateway를 이전 상태로 다시 시작한다.

동일 lock을 다시 적용하면 `result=no-op`, `gateway_restarted=no`가 나와야
한다.

## 수동 Update

자동 update나 recurring job은 사용하지 않는다. 먼저 upstream 차이만
확인한다.

```bash
bin/hermes-remote check-hallmark-update
```

이 명령은 checkout을 변경하지 않고 `origin/main`을 fetch해 고정 commit과
upstream commit 사이의 version, tree hash, diff stat, changed files를
출력한다. 실제 prompt 변경은 별도로 검토한다.

원격 Mac에서 전체 diff를 검토한다.

```bash
ssh bobeen \
  'git -C ~/.hermes/profiles/product/skill-sources/hallmark \
  diff <locked-commit> origin/main -- skills/hallmark'
```

승인할 commit이 정해지면 별도 review branch에서
`config/skills/hallmark.lock`의 `version`, `commit`, `tree`,
`skill_file_count`를 함께 갱신한다. 변경 검토와 승인이 끝난 뒤 다시
적용한다.

```bash
bin/hermes-remote setup-hallmark
bin/hermes-remote verify-hallmark
```

## 검증 기준

`verify-hallmark`는 다음을 모두 확인한다.

- checkout HEAD와 skill tree가 lock과 일치하고 Git 상태가 clean
- skill tree가 lock에 기록된 수의 일반 Markdown 파일로만 구성
- symlink, submodule, executable, non-Markdown file 부재
- `product`의 enabled skill 목록에 `hallmark` 존재
- default, `content`, `jarvis`, `preflight`에는 `hallmark` 부재
- product gateway 정상
- Hallmark `audit` verb가 inline HTML을 읽기 전용으로 진단하고 파일을 만들지 않음

`hermes skills audit`은 Hub-installed skill만 검사한다. Hallmark는
external skill이므로 위의 deterministic tree validation과 실제 read-only
smoke를 사용한다.

현재 product의 기본 `openai/gpt-oss-120b` one-shot 경로는 Hallmark를
빼도 `413 Request payload too large`를 반환한다. 이는 Hallmark 설치와
독립적으로 재현되는 기존 provider/model 제한이다. 설치 검증 smoke는
product 설정을 바꾸지 않고 `--model openai/gpt-5-nano`를 해당 호출에만
적용한다. product 기본 모델 또는 provider 변경은 이 runbook의 범위가
아니며 별도 승인 작업으로 다룬다.

## Rollback

실패한 `setup-hallmark`는 자동으로 직전 config와 checkout을 복구한다.
적용 후 사람이 rollback할 때는 명령 출력에 기록된 backup 경로를 사용한다.

1. 현재 product `config.yaml`을 별도 타임스탬프 backup한다.
2. `config_backup`을 product `config.yaml`로 복원한다.
3. 현재 checkout을 보존 경로로 이동하고 `checkout_backup`을 `hallmark`로 되돌린다.
4. `hermes --profile product gateway restart`와 `gateway status`를 실행한다.
5. `bin/hermes-remote verify-hallmark`로 복구 상태를 확인한다.

원격 backup이나 failed checkout은 검토 없이 삭제하지 않는다.

## 완료 기록

- task type: `remote-config` + `ops-change`
- HIL status: `completed`
- branch/worktree: 구현 branch와 격리 worktree
- changed files: lock, remote command, runbook, source ledger
- checks: shell syntax, SSH/status, update check, setup, idempotency, verify
- source ledger: `research/sources/2026-07-26-hallmark-product-skill.jsonl`
- completion mode: `review-required`
