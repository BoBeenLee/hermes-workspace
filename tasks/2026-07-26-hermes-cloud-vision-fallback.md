# Hermes Cloud Vision Fallback

- Task type: `remote-config` and `ops-change`
- HIL status: completed; the user explicitly requested reinforcement of the
  missing vision-provider behavior
- Target: default remote Mac `bobeen`, installed Hermes checkout
  `/Users/bobeenlee/.hermes/hermes-agent`, and profiles `default`, `content`,
  `product`, `jarvis`, and `preflight`
- Goal: provide a reliable Google AI Studio → OpenRouter → GroqCloud auxiliary
  vision route whose OCR result can be handed to a text-only Laguna S 2.1 model
- Secret handling: existing provider keys stayed in remote `.env`; no key value
  was copied into source, config YAML, logs, or task artifacts
- Completion mode: `review-required`

## Implemented

- Created remote code branch `codex/vision-fallback` at commit `72bc6b79e`.
- Scoped fallback-chain continuation to the `vision` auxiliary task. A failed
  configured candidate is quarantined and the next configured entry is tried
  after rate limits, connection failures/timeouts, model incompatibility, or
  malformed responses.
- Preserved the existing non-vision stale-credential and failure behavior.
- Changed the auxiliary image prompt to treat image text as untrusted data and
  return one JSON object with `summary`, `ocr_text`, `code_blocks`, `regions`,
  `uncertainties`, and `answer`.
- Configured all five profiles with:
  - primary: Google `gemini-3.6-flash`
  - fallback 1: OpenRouter `google/gemma-4-26b-a4b-it:free`
  - fallback 2: Groq `qwen/qwen3.6-27b`
  - JSON-object response mode, temperature `0.1`, and per-route timeouts

## Verification

- `453` Hermes tests passed across `tests/agent/test_auxiliary_client.py` and
  `tests/tools/test_vision_tools.py`.
- Python compilation and `git diff --check` passed in the installed Hermes
  checkout.
- All five YAML files parsed successfully, matched the intended vision route,
  and were structurally identical to their backups outside the intended
  `auxiliary.vision` keys.
- Google direct smoke: valid JSON, exact invoice ID, total, and code OCR.
- OpenRouter direct smoke: valid JSON, exact invoice ID, total, and code OCR.
- Hermes built-in `vision_analyze` end-to-end smoke through Google: valid
  normalized JSON and exact OCR.
- Groq key authentication reached the API, but the organization returned
  `403 model_permission_blocked_org` for `qwen/qwen3.6-27b`. The model is the
  only current vision-capable entry exposed by that account's Models API.
- Default, content, product, jarvis, and preflight gateways restarted and are
  running under launchd with new PIDs.

## Rollback

The timestamped config backups use suffix
`.vision-fallback.20260726-165609.bak`. Restore the matching file for each
profile, then restart that profile's gateway. The code rollback is switching
the installed checkout away from `codex/vision-fallback` after review.

## Review Required

- A Groq organization administrator must enable `qwen/qwen3.6-27b` before the
  third route is usable. Until then, Google and OpenRouter are the two verified
  working routes.
- The installed Hermes branch is local-only and was not pushed to the upstream
  NousResearch repository.
