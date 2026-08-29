---
type: Tool
title: Local LLM Providers
description: Operational guide for OpenAI-compatible local providers such as Ollama, vLLM, SGLang, and DGX Spark model services.
resource: repo://hermes-workspace/knowledge/tools/local-llm-providers.md
tags: [hermes, llm, providers]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/local-llm-providers.md
---

# Local LLM Providers

This runbook covers Hermes Agent model providers backed by local, self-hosted, or custom OpenAI-compatible endpoints such as Ollama, vLLM, SGLang, DGX Spark model services, and internal routing gateways.

Use this when Hermes can start but chat, tool use, or gateway work fails because no model provider is configured, the model endpoint is unreachable, or the provider was registered with the wrong API compatibility mode.

## Operating Model

Hermes provider setup is remote host state. Do not commit provider secrets, copied provider config, `~/.hermes/auth.json`, or `~/.hermes/.env`.

For local engines, prefer this shape:

```text
Hermes host -> loopback or SSH tunnel -> model server /v1 endpoint
```

Keep model services bound to loopback whenever practical. Use SSH tunnels for DGX Spark, remote Linux workstations, or another host on the tailnet. Expose model ports directly only when the user explicitly asks and the network risk is reviewed.

## Hermes Provider Setup

Start from the active Hermes host:

```bash
cd "$HERMES_REMOTE_WORKSPACE"
hermes
```

Open the model/provider selector:

```bash
hermes model
```

When Ollama, vLLM, or SGLang is not offered as a first-class provider, choose a custom endpoint and enter:

- Base URL: the OpenAI-compatible endpoint ending in `/v1`.
- API key: leave empty for local engines that do not require one.
- API compatibility mode: use automatic detection first; use OpenAI Chat Completions when the server is known to expose that format.
- Model name: use the exact model name exposed by the server. For vLLM and SGLang this is often the `--served-model-name` value.
- Context size: allow auto-detect first; if Hermes reports that the context is too small, set at least `65536`.
- Display name: use a short engine or host name such as `ollama`, `vllm-dgx`, or `sglang-dgx`.

After registering, select that provider as the default and run a short chat smoke test. If the provider was registered incorrectly, the simplest recovery is usually to delete it from `hermes model` and recreate it with the correct endpoint, model name, and compatibility mode.

Provider config changes are `remote-config` work and finish as `review-required`.

## Current Remote Mac Routing

Last checked from the control host on 2026-08-21:

```bash
bin/hermes-remote check-ssh
bin/hermes-remote status
```

The default macOS Hermes host is `bobeen` / `bobeenlee` and its runtime currently reports:

| Profile | Primary provider | Primary model |
| --- | --- | --- |
| `default` | `custom:mlx-qwen` | `lmstudio-community/Qwen3.8-27B-MLX-4bit` |
| `jarvis` | `custom:mlx-qwen` | `lmstudio-community/Qwen3.8-27B-MLX-4bit` |

`content`, `product`, and `preflight` were deleted on 2026-08-29. Both remaining
profiles are local-primary and fall back in this order:

```yaml
# default and jarvis
fallback_providers:
  - provider: custom:altalt
    model: openai/gpt-5-nano
    base_url: https://api.altalt.io/v1
  - provider: openrouter
    model: poolside/laguna-s-2.1:free
    base_url: https://openrouter.ai/api/v1
  - provider: groq
    model: openai/gpt-oss-120b
    base_url: https://api.groq.com/openai/v1
```

Verify a chain from the host with
`hermes fallback list` (or the `jarvis` wrapper): Hermes prints
`(via custom:altalt)` for custom-provider entries, which is the cheapest proof
that a hand-edited chain parsed.

A custom provider referenced by a profile's `model:` block must also be defined
in that profile's own `custom_providers`. A profile does not inherit
`custom_providers` from `~/.hermes/config.yaml`; the missing block fails at run
time with `Unknown provider 'custom:mlx-qwen'`, not at config load.

Hermes rejects any primary model whose context window is below `64000`
("Choose a model with at least 64K context"), so `context_length: 65536` is the
floor for a local provider, not a preference.

```yaml
custom_providers:
  - name: mlx-qwen
    base_url: http://127.0.0.1:8080/v1
    api_mode: chat_completions
    model: lmstudio-community/Qwen3.8-27B-MLX-4bit
    models:
      lmstudio-community/Qwen3.8-27B-MLX-4bit:
        context_length: 65536
```

### MLX Server On The Remote Mac

`mlx_lm.server` runs under launchd as `ai.hermes.mlx-qwen`, bound to
`127.0.0.1:8080`, started by
`/Users/bobeenlee/Workspaces/local-llm/scripts/start-mlx-qwen.sh`. Models live
in the Hugging Face cache and are exposed to the script through a symlink under
`~/Workspaces/local-llm/models/`. Logs are in `~/Workspaces/local-llm/logs/`.

The stock `mlx_lm.server` defaults are unsafe for a large dense model on a 32GB
Mac. Defaults keep up to `10` distinct KV caches (`--prompt-cache-size`) and
batch `32` decodes / `8` prompts at once. The 27B dense Qwen3.x models cost
about `0.25MB` of KV per token (64 layers, 4 KV heads, head_dim 256), so a
couple of cached agent prompts on top of `16.1GB` of weights aborts the process:

```text
libc++abi: terminating due to uncaught exception of type std::runtime_error:
[METAL] Command buffer execution failed: Insufficient Memory
```

launchd `KeepAlive` restarts it, so the symptom reaching the user is a macOS
"Python quit unexpectedly" report plus a stalled agent run. The serving flags
that hold the footprint down:

```text
--prompt-cache-size 1
--prompt-cache-bytes 4294967296
--decode-concurrency 1
--prompt-concurrency 1
--prefill-step-size 512
--max-tokens 4096
--chat-template-args '{"enable_thinking":false}'
```

Measured on this host with a fixed 256-token completion, three runs, median:

| Model | Weights | KV per token | Throughput |
| --- | --- | --- | --- |
| `samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed` (MoE, A3B) | 19GB | 0.08MB | `40.1 tok/s` |
| `lmstudio-community/Qwen3.6-27B-MLX-4bit` (dense) | 16.1GB | 0.25MB | `10.3 tok/s` |
| `lmstudio-community/Qwen3.8-27B-MLX-4bit` (dense, current) | 16.1GB | 0.25MB | `10.2 tok/s` |

A dense 27B is roughly `4x` slower than the A3B MoE it replaced even though its
weights are smaller, and a Qwen3.6 → 3.8 upgrade does not move that number:
the two share layer count, KV heads, head_dim, vocab, and quantization, so they
are interchangeable at the serving layer and identical in cost. Budget for the
speed before pointing an interactive profile at a dense local model.

MTP draft repos such as `mlx-community/Qwen3.8-27B-MTP-4bit` cannot be used as
`--draft-model` here: they carry `model_type: qwen3_5_mtp`, and mlx-lm `0.31.3`
ships only `qwen3_5.py` and `qwen3_5_moe.py`. Speculative decoding needs either
a newer mlx-lm with that module or a self-contained MTPLX-style conversion whose
`model_type` is a supported one.

## Cloud Vision Bridge

Last verified on the remote Mac on 2026-07-26, all five Hermes profiles use
the same auxiliary vision route:

1. Google AI Studio: `gemini-3.6-flash`
2. OpenRouter: `google/gemma-4-26b-a4b-it:free`
3. GroqCloud: `qwen/qwen3.6-27b`

The route is separate from the profiles' primary text models. It converts an
image into one JSON object with `summary`, `ocr_text`, `code_blocks`,
`regions`, `uncertainties`, and `answer`, which can be passed to a text-only
model such as Laguna S 2.1. Text found inside an image is treated as untrusted
data and is never followed as an instruction.

Secret-safe configuration shape:

```yaml
auxiliary:
  vision:
    provider: gemini
    model: gemini-3.6-flash
    base_url: ""
    timeout: 120
    temperature: 0.1
    extra_body:
      response_format:
        type: json_object
    fallback_chain:
      - provider: openrouter
        model: google/gemma-4-26b-a4b-it:free
        timeout: 60
      - provider: groq
        model: qwen/qwen3.6-27b
        timeout: 45
```

The installed Hermes checkout contains a vision-only fallback hardening patch
on branch `codex/vision-fallback`, commit `72bc6b79e`. A failed configured
candidate advances to the next entry on rate limits, timeouts, model
incompatibility, or an invalid response. Other auxiliary tasks retain their
existing fallback behavior.

Verification status:

- Google returned valid structured JSON and exact OCR for the synthetic test
  invoice through the built-in `vision_analyze` tool.
- OpenRouter Gemma 4 returned valid structured JSON and exact OCR through its
  API.
- Groq accepted the API key, but the organization currently blocks
  `qwen/qwen3.6-27b`. The entry remains third in the chain and will be
  temporarily quarantined if reached until an administrator enables the model.
- The relevant Hermes test suites passed `453` tests.
- The five gateway profiles restarted successfully and remained supervised by
  launchd.

Remote rollback copies were created before the config change. The
`content`/`product`/`preflight` copies went with those profiles on 2026-08-29,
and the `jarvis` copy was pruned in the same cleanup; only the `default` copy
still exists:

```text
/Users/bobeenlee/.hermes/config.yaml.vision-fallback.20260726-165609.bak
/Users/bobeenlee/.hermes/profiles/content/config.yaml.vision-fallback.20260726-165609.bak
/Users/bobeenlee/.hermes/profiles/product/config.yaml.vision-fallback.20260726-165609.bak
/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.vision-fallback.20260726-165609.bak
/Users/bobeenlee/.hermes/profiles/preflight/config.yaml.vision-fallback.20260726-165609.bak
```

Do not put Google, OpenRouter, or Groq keys in YAML or git. They remain in the
remote Hermes `.env`. Enabling the Groq vision model is an external
organization-policy change and requires separate operator review.

## Altalt Routing

Since 2026-08-21 `altalt` is the first fallback of the `default` and `jarvis`
profiles rather than their primary:

1. Primary: `custom:mlx-qwen`, local MLX `lmstudio-community/Qwen3.8-27B-MLX-4bit`.
2. Fallback 1: `altalt` custom OpenAI-compatible endpoint, model `openai/gpt-5-nano`.
3. Fallback 2: OpenRouter `poolside/laguna-s-2.1:free`.
4. Fallback 3: Groq.

Hermes tries `fallback_providers` in list order when the primary model fails.

This is compatible with Hermes v0.18.0 because custom providers support `extra_headers`, and those headers are merged into OpenAI client `default_headers` for matching `base_url` entries. Use `extra_headers` for gateways that require headers such as `X-Machine-ID`.

Altalt accepts `X-Machine-ID` authentication and rejects requests that also include an `Authorization` bearer header. Hermes uses the OpenAI SDK for custom endpoints, and the SDK normally sends a placeholder bearer token for no-key custom providers. For altalt, explicitly blank the Authorization header in the same `extra_headers` block.

Do not hard-code the real machine ID in git-tracked docs, shell history, or task artifacts. Treat it like a credential. Keep it only in the remote Hermes host config or secret store.

Secret-safe YAML shape:

```yaml
model:
  provider: custom:altalt
  default: openai/gpt-5-nano
  base_url: https://api.altalt.io/v1
  api_mode: chat_completions

custom_providers:
  - name: altalt
    base_url: https://api.altalt.io/v1
    api_mode: chat_completions
    model: openai/gpt-5-nano
    extra_headers:
      Authorization: ""
      X-Machine-ID: "<remote-only-machine-id>"
    models:
      openai/gpt-5-nano: {}

fallback_providers:
  - provider: openrouter
    model: poolside/laguna-s-2.1:free
    base_url: https://openrouter.ai/api/v1
  - provider: groq
    model: openai/gpt-oss-120b
    base_url: https://api.groq.com/openai/v1
```

Equivalent endpoint smoke test shape, with the real `X-Machine-ID` supplied only on the remote host:

```bash
curl https://api.altalt.io/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "X-Machine-ID: $ALTALT_MACHINE_ID" \
  -d '{"model":"openai/gpt-5-nano","messages":[{"role":"user","content":"test"}],"stream":false}'
```

After editing remote `~/.hermes/config.yaml`, verify and restart:

```bash
bin/hermes-remote model-status
bin/hermes-remote gateway-restart
bin/hermes-remote status
```

Provider changes on the remote Mac are `remote-config` work: create or rely on a timestamped backup before editing, do not print secrets, and finish as `review-required`.

The 2026-07-06 `altalt` switches created remote backups at:

```text
/Users/bobeenlee/.hermes/config.yaml.bak-altalt-20260706-231404
/Users/bobeenlee/.hermes/profiles/jarvis/config.yaml.bak-altalt-20260706-231932
```

## Endpoint Patterns

### Ollama

Default endpoint:

```text
http://127.0.0.1:11434/v1
```

If Hermes and Ollama run in the same OS account or same Linux environment, loopback is usually correct. If Hermes runs inside WSL while Ollama runs on Windows, `127.0.0.1` from WSL may not reach the Windows Ollama process. In that case, configure Ollama to listen beyond loopback and use the Windows host IP in the Hermes Base URL:

```text
http://<windows-host-ip>:11434/v1
```

Only bind Ollama beyond loopback after reviewing who can reach that port.

### vLLM

Common OpenAI-compatible endpoint:

```text
http://127.0.0.1:8000/v1
```

For Hermes agent use, the serving arguments matter as much as the endpoint:

- `--max-model-len 65536` or higher when the model supports it.
- `--served-model-name <name>` so Hermes can register a stable model name.
- `--enable-auto-tool-choice` when tool calling is needed.
- `--tool-call-parser <parser>` matching the model family.
- `--reasoning-parser <parser>` matching the model family when reasoning output is used.

For Qwen Coder style models, verify the currently supported parser names in the vLLM documentation before starting the server.

### SGLang

Common OpenAI-compatible endpoint:

```text
http://127.0.0.1:8000/v1
```

Use the same provider registration pattern as vLLM. Important serving arguments usually include:

- `--context-length 65536` or higher when the model supports it.
- `--served-model-name <name>`.
- tool-call parser and reasoning parser values that match the model family.

Verify the parser names against the installed SGLang version before changing a production Hermes provider.

## DGX Spark As A Provider

Use [DGX Spark Remote Access](../runbooks/dgx-spark-remote-access.md) for the DGX access path. Keep the model server bound to loopback on the DGX, then tunnel it to the Hermes host or control host.

Example tunnel from the control host to the DGX model service:

```bash
ssh -N \
  -L 8000:127.0.0.1:8000 \
  bobeenlee@172.30.1.87
```

Then register this Base URL from the machine where Hermes runs:

```text
http://127.0.0.1:8000/v1
```

If Hermes runs on a different remote host than the control host, create the tunnel from the Hermes host or use SSH forwarding that terminates where Hermes can reach it.

## Verification

From the control host, the helper can test raw endpoints:

```bash
bin/hermes-remote check-llm-endpoint http://127.0.0.1:8000/v1
```

From the Hermes host, inspect model/provider state without printing secrets:

```bash
bin/hermes-remote model-status
```

For endpoint-level checks:

```bash
curl -sS http://127.0.0.1:8000/v1/models
```

For Hermes-level checks:

```bash
hermes model
hermes -z "Reply with OK and then list the tools you can see, if any."
```

If gateway jobs fail after a provider change, restart and re-check:

```bash
bin/hermes-remote gateway-restart
bin/hermes-remote status
```

## Triage

Use this order:

1. Confirm the model server process is running on the host that owns it.
2. Confirm the service is bound to the expected interface and port.
3. Confirm `/v1/models` responds from the same network namespace where Hermes runs.
4. Confirm Hermes registered the exact model name exposed by the server.
5. Confirm context length is at least `65536` when Hermes requires it.
6. Confirm API compatibility mode matches the server.
7. Confirm tool-call parser and reasoning parser match the model family.
8. Recreate the provider if the interactive Hermes model config is easier to replace than edit.

Common failure signals:

- `connection refused`: server is down, port is wrong, or the tunnel is not open.
- `models endpoint empty`: server is up but the model did not load.
- `model not found`: Hermes provider model name does not match the served model name.
- tool calls ignored or malformed: parser or compatibility mode mismatch.
- context-size error: set a larger context size or choose a model/server configuration that supports it.
