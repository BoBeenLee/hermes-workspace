---
type: Workflow
title: Research Analysis
description: Research workflow for market, product, competitor, pricing, legal, policy, and trend analysis.
resource: repo://hermes-workspace/knowledge/workflows/research-analysis.md
tags: [hermes, research, sources]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/research-workflow.md
---

# Research Workflow

The Research Analysis module sits behind the Workspace Lifecycle module. Use it for market research, product analysis, competitor review, pricing checks, legal/policy scans, and trend reports.

## When To Use Web Verification

Always verify with web sources when the task involves:

- current or recent market trends
- prices, plans, products, model names, or vendor claims
- law, policy, compliance, or platform rules
- competitors or recommendations
- anything likely to have changed

Prefer primary sources for technical, legal, financial, or product claims. Record sources in the source ledger.

## Artifact Contract

Research-based work writes four artifacts:

```text
research/briefs/<YYYY-MM-DD>-<slug>.md
research/sources/<YYYY-MM-DD>-<slug>.jsonl
research/notes/<YYYY-MM-DD>-<slug>.md
reports/<YYYY-MM-DD>-<slug>.md
```

### Brief

The brief records:

- question
- scope
- region
- time period
- exclusions
- output format
- freshness requirement

### Source Ledger

The source ledger is JSONL, one source per line:

```json
{"url":"https://example.com","title":"Example","publisher":"Example Inc.","retrieved_at":"2026-06-06T00:00:00Z","relevance":"why this source matters","trust_note":"primary source / official docs / trade press / secondary analysis"}
```

### Notes

Notes record:

- observations
- counter-evidence
- uncertain claims
- source conflicts
- assumptions

### Report

The report includes:

- conclusion
- evidence
- market signals
- risks
- open questions
- next research suggestions

## Completion Rules

Report-only research can finish as `done` when the artifacts are present and the source ledger supports the claims.

Use `review-required` when the research task also creates or modifies:

- data collection scripts
- recurring analysis automation
- remote Hermes config
- GitHub Actions or external publishing flows
- anything that spends money or changes production-like behavior

Research Intelligence + GTM enrichment tasks use the same artifact contract plus an artifact directory under `artifacts/research-intel/<date>-<slug>/`. Clay enrichment starts as a dry-run. Real Clay spend, cookie-backed access, OAuth/auth changes, gateway integration, scheduled jobs, CRM writes, and outbound sending always require human review and finish as `review-required`.

## Example Request

```text
Hermes, 2026년 국내 AI 채용 시장에서 ML engineer 수요를 조사하고 주간 리포트로 정리해줘.
```

Expected output paths:

```text
research/briefs/2026-06-06-ai-ml-engineer-demand-kr.md
research/sources/2026-06-06-ai-ml-engineer-demand-kr.jsonl
research/notes/2026-06-06-ai-ml-engineer-demand-kr.md
reports/2026-06-06-ai-ml-engineer-demand-kr.md
```

Completion note:

```text
task type: market-research
branch/worktree: hermes/<task> at .worktrees/<task>
report: reports/<YYYY-MM-DD>-<slug>.md
source ledger: research/sources/<YYYY-MM-DD>-<slug>.jsonl
checks: artifact files present, source ledger reviewed
completion mode: done
```
