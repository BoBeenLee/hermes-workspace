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

This runbook covers Hermes Agent model providers backed by local or self-hosted OpenAI-compatible endpoints such as Ollama, vLLM, SGLang, or a DGX Spark model service.

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
