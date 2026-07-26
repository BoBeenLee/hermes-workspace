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

Last checked from the control host on 2026-07-06:

```bash
bin/hermes-remote check-ssh
bin/hermes-remote status
```

The default macOS Hermes host is `bobeen` / `bobeenlee` and its runtime currently reports:

| Profile | Primary provider | Primary model |
| --- | --- | --- |
| `default` | `custom:altalt` | `openai/gpt-5-nano` |
| `jarvis` | `custom:altalt` | `openai/gpt-5-nano` |
| `content` | `groq` | `openai/gpt-oss-120b` |
| `product` | `groq` | `openai/gpt-oss-120b` |
| `preflight` | `custom:mlx-qwen` | `samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed` |

The `default` and `jarvis` profiles currently fall back to OpenRouter, then Groq:

```yaml
fallback_providers:
  - provider: openrouter
    model: openrouter/free
    base_url: https://openrouter.ai/api/v1
  - provider: groq
    model: openai/gpt-oss-120b
    base_url: https://api.groq.com/openai/v1
```

The named `content`, `product`, and `preflight` profiles were not changed during the 2026-07-06 `altalt` default-profile and `jarvis` switches; at that time they still had the single OpenRouter fallback. The `preflight` profile and default config also include a local MLX Qwen provider:

```yaml
custom_providers:
  - name: mlx-qwen
    base_url: http://127.0.0.1:8080/v1
    api_mode: chat_completions
    model: samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed
    models:
      samuelfaj/Qwen3.6-35B-A3B-4bit-MTPLX-Optimized-Speed:
        context_length: 65536
```

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

Remote rollback copies were created before the config change:

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

The `default` and `jarvis` profile routes are configured as:

1. Primary: `altalt` custom OpenAI-compatible endpoint, model `openai/gpt-5-nano`.
2. Fallback 1: OpenRouter.
3. Fallback 2: Groq.

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
    model: openrouter/free
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
