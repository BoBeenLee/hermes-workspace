# Workspace Lifecycle

The Workspace Lifecycle module is the deep interface for Hermes work in this repo. Hermes uses it for ops script changes, remote config changes, incident triage, market research, and analysis reports.

## Canonical Workspace

The remote Hermes workspace is:

```text
/Users/bobeenlee/Workspaces/hermes-remote-ops
```

Hermes should run from that repo root and use git worktree isolation:

```yaml
terminal:
  cwd: "/Users/bobeenlee/Workspaces/hermes-remote-ops"

worktree: true
```

For one-shot CLI work:

```bash
cd /Users/bobeenlee/Workspaces/hermes-remote-ops
hermes -w
```

## Task Types

| Type | Use when | Required outputs | Completion mode |
|------|----------|------------------|-----------------|
| `ops-change` | Editing `bin/`, `scripts/`, docs that change operating behavior | Branch/worktree, changed files, tests/checks | `review-required` unless docs-only |
| `remote-config` | Editing or proposing edits to `~/.hermes/config.yaml`, launchd, gateway, keys, auth, or local permissions | Backup path, exact change summary, verification commands | `review-required` |
| `incident-triage` | Investigating Discord threads, gateway logs, failed tasks, provider failures | Thread/log reference, status, likely cause, next action | `done` if no change; otherwise `review-required` |
| `market-research` | Gathering current market information, competitors, products, pricing, policy, or trends | Brief, source ledger, notes, report path | `done` if report-only |
| `analysis-report` | Synthesizing existing evidence into a durable report | Inputs, assumptions, report path | `done` if report-only |

## Required Interface

Every task must leave a concise completion note with:

- task type
- branch and worktree path, or `none` for read-only work
- changed files or report path
- tests/checks run
- source ledger path when research-based
- completion mode: `done` or `review-required`

Use `review-required` for:

- code or shell script changes
- data collection scripts or recurring automation
- remote config changes
- gateway restart, launchd changes, permission grant, key/auth changes
- any task where merge or operational application needs human approval

## Forbidden Outputs

Never commit or paste:

- `.env`
- SSH private keys
- provider API keys or OAuth tokens
- Discord tokens
- `~/.hermes/.env`
- `~/.hermes/auth.json`
- copied remote secret files
- raw provider config output that includes secrets

Summarize secret status without copying values.

## Artifact Layout

```text
tasks/
reports/
research/
  briefs/
  sources/
  notes/
artifacts/
```

Use `tasks/` for task handoffs and durable work notes. Use `artifacts/` only for non-secret outputs that do not fit reports or research.

## Verification

For docs-only changes:

```bash
rg -n "Workspace Lifecycle|Research Analysis|review-required|source ledger" .
git diff -- .
```

For ops script changes:

```bash
bash -n bin/hermes-remote
bin/hermes-remote check-ssh
bin/hermes-remote status
```

For research tasks:

```bash
test -f research/briefs/<YYYY-MM-DD>-<slug>.md
test -f research/sources/<YYYY-MM-DD>-<slug>.jsonl
test -f reports/<YYYY-MM-DD>-<slug>.md
```
