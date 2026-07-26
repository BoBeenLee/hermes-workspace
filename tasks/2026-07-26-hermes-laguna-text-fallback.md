# Hermes Laguna Text Fallback

- Task type: `remote-config`
- HIL status: completed
- Approval summary: replace only the `openrouter/free` text fallback with
  `poolside/laguna-s-2.1:free` in the default, content, product, jarvis, and
  preflight profiles; do not change primary models, vision routing, Groq,
  authentication, or recurring automation; verify with backups, structural
  YAML comparison, provider smoke checks, gateway restarts, and status checks
- Target: default remote Mac `bobeen`
- Branch and worktree: none for the remote config
- Completion mode: `review-required`

## Change

The first entry in `fallback_providers` now uses:

```yaml
- provider: openrouter
  model: poolside/laguna-s-2.1:free
  base_url: https://openrouter.ai/api/v1
```

This was applied to:

- `/Users/bobeenlee/.hermes/config.yaml`
- `/Users/bobeenlee/.hermes/profiles/content/config.yaml`
- `/Users/bobeenlee/.hermes/profiles/product/config.yaml`
- `/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml`
- `/Users/bobeenlee/.hermes/profiles/preflight/config.yaml`

Primary text models, Groq fallbacks, and every `auxiliary.vision` route were
left unchanged.

## Backups

The pre-change copies use suffix
`.laguna-fallback.20260726-201013.bak`:

- `/Users/bobeenlee/.hermes/config.yaml.laguna-fallback.20260726-201013.bak`
- `/Users/bobeenlee/.hermes/profiles/content/config.yaml.laguna-fallback.20260726-201013.bak`
- `/Users/bobeenlee/.hermes/profiles/product/config.yaml.laguna-fallback.20260726-201013.bak`
- `/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.laguna-fallback.20260726-201013.bak`
- `/Users/bobeenlee/.hermes/profiles/preflight/config.yaml.laguna-fallback.20260726-201013.bak`

## Verification

- OpenRouter Models API listed `poolside/laguna-s-2.1:free` as text-only with
  zero prompt and completion price.
- Each current YAML file parsed successfully.
- Structural comparison against each backup found exactly one changed value:
  `fallback_providers[0].model`.
- The direct Laguna smoke reached OpenRouter but returned HTTP 429 at the time
  of the change. The fixed free endpoint can therefore be temporarily
  unavailable; Hermes retains its next configured Groq fallback where present.
- All five launchd-supervised gateways were restarted.
- Source ledger:
  `research/sources/2026-07-26-openrouter-laguna-fallback.jsonl`

## Review Required

Confirm acceptable behavior under Laguna free-route rate limiting. The
`default` and `jarvis` profiles can continue to Groq after the OpenRouter
failure. The `content`, `product`, and `preflight` profiles currently have no
second text fallback after Laguna.
