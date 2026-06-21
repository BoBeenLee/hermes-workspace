# Hermes Mac Research Intelligence Roadmap

## Summary

The post-pilot goal is to move verified CLI behavior into Hermes operations in stages:

```text
pilot CLI -> Hermes command integration -> approved workflow -> recurring research operations
```

Clay cost, cookie access, OAuth authentication, and external platform policy risk stay behind approval gates and audit logs.

## Phase 1: Pilot Evaluation

Evaluate research quality, source-ledger coverage, Clay dry-run value, cost risk, and failure paths.

Required outputs:

```text
reports/<date>-research-intel-pilot-evaluation.md
tasks/research-intel-next-steps.md
```

Success criteria:

- Candidate company/person recommendations are source-backed.
- Clay enrichment is useful relative to expected cost.
- Public data routes degrade gracefully when OAuth or cookie routes fail.

## Phase 2: Hermes Command Integration

Promote only verified functions into `bin/hermes-remote`:

- `research-intel-doctor`
- `research-intel-init-policy`
- `research-intel-xai-smoke`
- `research-intel-xai-search`
- `research-intel-clay-smoke`
- `research-intel-collect`
- `research-intel-enrich`
- `research-intel-report`
- `research-intel-evaluate`

Gateway automation remains out of scope.

## Phase 3: Approved Hermes Workflow

Discord or Hermes research/GTM requests must pass the HIL Gate before execution.

Approval Summary must include:

- research purpose
- target market/company/person scope
- allowed data sources
- cookie use decision
- Clay use decision and budget limit
- output format

After approval, Hermes runs the task as `market-research` or `analysis-report`. Clay spend, cookie access, and remote config changes finish as `review-required`.

## Phase 4: MCP Tool Layer

After manual CLI routes are stable, wrap them as least-privilege MCP tools:

- public collection tool
- OAuth-based X/Grok tool
- cookie-backed session tool
- Clay enrichment tool
- source ledger writer

Clay tools default to dry-run and require explicit budget and approval parameters for spend.

xAI stays a research-channel tool. Do not make xAI the default Hermes provider unless a separate remote-config task explicitly approves that change.

## Phase 5: Recurring Research Operations

Promote only specific reviewed use cases:

- weekly AI agent market and competitor report
- GitHub/RSS/YouTube/X trend watch for a product category
- partnership account discovery
- GTM list generation from investment, hiring, and launch signals

Start with manual runs, then move to Kanban or scheduled jobs after review.

## Phase 6: Dashboard And Observability

Use generated HTML dashboards to review:

- source success and failure
- source-ledger coverage
- candidate scoring
- Clay enrichment success
- expected and actual credit usage
- cookie/OAuth usage history

The operating goal is traceability: a human should be able to see what Hermes believed and why.
