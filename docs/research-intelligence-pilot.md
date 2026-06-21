# Hermes Research Intelligence Pilot

This pilot turns the roadmap into a manual, auditable Research + GTM workflow for the Hermes Mac. It does not attach anything to the Hermes gateway, scheduled jobs, CRM, or outbound sending.

## Operating Model

The workflow has four manual steps:

1. `research-intel-doctor` checks tool readiness, policy gates, and secret presence without printing secrets.
2. `research-intel-collect` creates a research brief, source ledger, notes, report, raw records, candidate seeds, and an audit log.
3. `research-intel-enrich` prepares a Clay enrichment dry-run from reviewed candidates.
4. `research-intel-report` and `research-intel-evaluate` generate the review dashboard, pilot evaluation, and next-step task note.

Completion mode is `done` only for report-only artifact generation. Any authentication change, cookie-backed access, Clay spend, gateway integration, or recurring automation remains `review-required`.

## Commands

Run from the control host:

```bash
bin/hermes-remote research-intel-doctor
bin/hermes-remote research-intel-init-policy
bin/hermes-remote research-intel-xai-smoke
bin/hermes-remote research-intel-clay-smoke
bin/hermes-remote research-intel-xai-search \
  --slug ai-agent-x-signals \
  --query "AI agent research automation GTM signals"
bin/hermes-remote research-intel-collect \
  --slug ai-agent-gtm \
  --query "AI agent research automation GTM candidates" \
  --url "https://github.com/Panniantong/agent-reach"
bin/hermes-remote research-intel-enrich \
  --input artifacts/research-intel/YYYY-MM-DD-ai-agent-gtm/candidates.jsonl \
  --max-records 5
bin/hermes-remote research-intel-report --artifact YYYY-MM-DD-ai-agent-gtm
bin/hermes-remote research-intel-evaluate --artifact YYYY-MM-DD-ai-agent-gtm
```

The wrapper streams `scripts/hermes/research_intel.py` to the remote Hermes workspace and runs it there, so the local repo remains the source of truth for the pilot script.

## Policy Gates

The default policy file is:

```text
~/.hermes/research-intel/policy.yaml
```

Cookie-backed routes require:

```yaml
allow_cookie_access: true
cookie_platforms:
  - linkedin
  - reddit
```

Clay spend requires:

```yaml
allow_clay_spend: true
```

The CLI still refuses live Clay spend until the official Clay MCP/API path is wired and reviewed. Dry-run enrichment is the default.

xAI is used only as a research signal channel:

```yaml
xai_research_enabled: true
xai_default_model: grok-4.3
```

Do not switch the default Hermes provider to xAI as part of this pilot.

## xAI Research Channel

Use:

```bash
bin/hermes-remote research-intel-xai-smoke
bin/hermes-remote research-intel-xai-search --query "<market or account signal question>"
```

`research-intel-xai-search` calls the xAI Responses API with the server-side `x_search` tool, writes an audit record, and creates a source ledger entry for the signal report.

## Clay No-Spend Check

Use:

```bash
bin/hermes-remote research-intel-clay-smoke
```

This verifies that the Clay key is present and that policy gates are readable. It does not call a live enrichment endpoint and does not spend Clay Actions or Data Credits.

## HIL Approval Summary Fields

Before Discord or Hermes requests use this workflow, the Approval Summary must include:

- research purpose
- target market, company, and person scope
- allowed data sources
- whether cookie access is allowed
- whether Clay is allowed and the budget limit
- output format
- completion mode

## Artifact Contract

Each collection writes:

```text
research/briefs/<date>-<slug>.md
research/sources/<date>-<slug>.jsonl
research/notes/<date>-<slug>.md
reports/<date>-<slug>.md
artifacts/research-intel/<date>-<slug>/
```

The artifact directory contains raw collection records, candidate seeds, enrichment dry-run rows, a dashboard, and an audit log.

## Promotion Rules

- Promote only source routes that have source-ledger evidence from the pilot.
- Keep public data and OAuth/API routes ahead of cookie-backed routes.
- Narrow candidate records before Clay enrichment.
- Do not create scheduled jobs until one manual recurring use case has passed review.
- Do not write to CRM or send outreach automatically.
