# Workspace Lifecycle

The Workspace Lifecycle module is the deep interface for Hermes work in this repo. Hermes uses it for ops script changes, remote config changes, incident triage, market research, analysis reports, and delegated implementation work.

## Canonical Workspace

Use the canonical workspace from the active target profile. For the current default macOS target it is:

```text
/Users/bobeenlee/Workspaces/hermes-workspace
```

Hermes should run from the target profile's repo root and use git worktree isolation:

```yaml
terminal:
  cwd: "/Users/bobeenlee/Workspaces/hermes-workspace"

worktree: true
```

For one-shot CLI work:

```bash
cd /Users/bobeenlee/Workspaces/hermes-workspace
hermes -w
```

For Linux targets, use the same lifecycle with the Linux profile's `HERMES_REMOTE_WORKSPACE`, commonly `/home/<user>/Workspaces/hermes-workspace`. Keep OS-specific paths in `.env` or `config/targets/<target>.env`; do not bake them into lifecycle rules.

## Discord HIL Gate

Discord requests pass through the Discord HIL Gate before this lifecycle when they are ambiguous or risky. Hermes uses the externally installed mattpocock `grill-me` skill to ask one question at a time in the original Discord thread.

Skip the gate for clear read-only status checks. Use the gate before any work where goal, success criteria, target workspace/repo, write scope, remote config/auth/deployment impact, recurring automation impact, Antigravity delegation, or standalone repo need is unclear.

No Workspace Lifecycle task may start until Hermes posts an Approval Summary and the user explicitly approves it. The Approval Summary must include:

- goal
- scope and non-goals
- target workspace or repo
- expected changes, or read-only status
- verification commands or checks
- completion mode: `done` or `review-required`

If the Approval Summary identifies a standalone service, product, app, site, tool, or repo, continue with the New Repository HIL Gate before creating repos, cloning workspaces, scaffolding, delegating, configuring deployment, or pushing branches.

## Task Types

| Type | Use when | Required outputs | Completion mode |
|------|----------|------------------|-----------------|
| `ops-change` | Editing `bin/`, `scripts/`, docs that change operating behavior | Branch/worktree, changed files, tests/checks | `review-required` unless docs-only |
| `remote-config` | Editing or proposing edits to `~/.hermes/config.yaml`, launchd, gateway, keys, auth, or local permissions | Backup path, exact change summary, verification commands | `review-required` |
| `incident-triage` | Investigating Discord threads, gateway logs, failed tasks, provider failures | Thread/log reference, status, likely cause, next action | `done` if no change; otherwise `review-required` |
| `market-research` | Gathering current market information, competitors, products, pricing, policy, or trends | Brief, source ledger, notes, report path | `done` if report-only |
| `analysis-report` | Synthesizing existing evidence into a durable report | Inputs, assumptions, report path | `done` if report-only |
| `delegated-implementation` | Asking Antigravity CLI to implement inside an isolated worktree while Hermes supervises | Antigravity session id, branch/worktree, artifact path, diff/check summary | `review-required` |
| `new-repo-hil` | A standalone service, product, app, site, or tool appears to need its own GitHub repo/workspace | Proposed owner, repo name, visibility, stack, deployment target, delegation mode | `review-required`; wait for approval before creation |

## Required Interface

Every task must leave a concise completion note with:

- task type
- HIL status: `skipped` or `completed`; if completed, include the Approval Summary and Discord thread id
- branch and worktree path, or `none` for read-only work
- changed files or report path
- tests/checks run
- source ledger path when research-based
- completion mode: `done` or `review-required`

Use `review-required` for:

- code or shell script changes
- data collection scripts or recurring automation
- remote config changes
- new repository/workspace creation or deployment setup
- gateway restart, launchd changes, permission grant, key/auth changes
- Antigravity delegated implementation
- any task where merge or operational application needs human approval

## New Repository HIL Gate

Hermes should infer whether a request belongs in the current repo or needs a new standalone repository. Examples that usually need the gate include "make a todo service", "create a new SaaS app", "build a separate landing site", or any request where product code should not live in `hermes-workspace`.

Before creating or cloning a new repo, Hermes must ask for HIL approval with:

- owner or org
- repo name
- visibility: `private` or `public`
- initial stack or scaffold
- deployment target
- Antigravity delegation mode

After approval, Hermes may create the repo, clone the workspace, scaffold, delegate implementation, verify, and deploy. The completion note must include the approved HIL values and end as `review-required`.

When delegating implementation for a new repo, Hermes must pass the approved repo workspace path to Antigravity. For example, use `/Users/bobeenlee/Workspaces/Todo` as the `workspace` argument for `antigravity_start_task`; do not let a standalone product task default back to `hermes-workspace`.

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
