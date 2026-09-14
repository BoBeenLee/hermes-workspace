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

## DGX parent and child chains (2026-09-14, measured)

The Altalt Routing section below is the **Mac era** (`custom:mlx-qwen` primary). It no
longer describes any live host.

The two roles want different things, and measuring both is what reordered this chain. A
parent turn needs low latency and has to survive several rooms firing at once; a child
fan-out needs throughput. Every number below is a real request carrying ~11k tokens, the
size of the daemon's 19 tool schemas plus room context.

| provider / model | serial | 6 parallel | sustained | binding limit |
|---|---|---|---|---|
| `custom:kilo` / `nex-agi/nex-n2.5-pro:free` | 3.0s | 6/6 in 4.3s | 745,919 tok/min | none observed |
| `custom:kilo` / `nvidia/nemotron-3-ultra-550b-a55b:free` | 3.4-19.7s | 6/6 in 19.7s | 201,701 tok/min | upstream 502 |
| `custom:kilo` / `nvidia/nemotron-3.5-lightning:free` | 30.6s | 6/6 in 51.4s | 77,777 tok/min | queueing |
| `opencode-free` / `nemotron-3-ultra-free` | 66.3s | 6/6 in 85.3s | 46,655 tok/min | queue latency |
| `zai` / `glm-4.7-flash` | **1 of 6 answered** | 2/6 | - | free tier overloaded |
| `custom:llama-local` / `Qwen3.8-27B-UD-Q6_K_XL.gguf` | 8.57 tok/s | n/a, `--parallel 1` | - | one slot |

Parent chain: `custom:kilo`/`nex-n2.5-pro:free` -> `opencode-free` -> `zai` -> `openrouter`
-> `custom:llama-local`.
Child chain (`delegation.*`): `custom:kilo`/`nemotron-3-ultra:free` ->
`custom:kilo`/`nex-n2.5-pro:free` -> `opencode-free` -> `openrouter` -> `zai`.

The demand side is what sizes this. `max_concurrent_children` 3 x `max_iterations` 20 is up
to 60 requests of ~11k tokens inside `child_timeout_seconds` 600, i.e. **132k tok/min**.
Only the Kilo rungs clear that. `max_iterations` came down from 40 because the old value
was chosen when the child model cost 24s per call; at 3s the extra iterations only spend
the hourly request budget.

### zai glm-4.7-flash free is overloaded, and it is not a TPM problem

It answered **1 of 6** serial requests spaced 10 seconds apart, and 2 of 6 in parallel,
always `429 {"code":1305,"message":"The service may be temporarily overloaded"}` or
`1302 Rate limit reached for requests`. The successes carried 15,413 prompt tokens without
complaint, so tokens are not the axis - **requests** are. This is why it stopped being the
parent: two 20-minute hard caps and a 409s turn that produced 15 characters, all on
2026-09-14, are this 429 burning through fallback rungs.

### Kilo gateway: keyless, no token ceiling found

`https://api.kilo.ai/api/gateway/v1` serves every `:free` slug with **no API key** -
`200 requests/hour per IP`, no account. Paid slugs answer `401 PAID_MODEL_AUTH_REQUIRED`.
22 free slugs as of 2026-09-14, including nemotron ultra/super/lightning, `nex-n2.5-pro`
and `-mini`, `ling-3.0-flash-vl` (vision), `north-mini-code`, `step-3.7-flash`.

Measured ceilings: a single 110,023-token request went through in 9.3s, so there is no
input cap to design around. 6 parallel 11k requests all returned; 12 parallel returned
3 of 12. **Six concurrent is the safe working point**, which is what
`max_concurrent_children` 3 plus a parent sits inside.

Upstream failures come back as **HTTP 200 with `{"error":{"code":502,"message":"Upstream
error from Nvidia: Service temporarily overloaded"}}`**. `agent/error_classifier.py` keys
off the HTTP status and cannot see it; the turn lands in
`agent/turn_response_check.py:258` instead ("Empty/malformed response - switching to
fallback"). That path is correct but spends a rung, which is why the child chain keeps a
second Kilo model directly behind the first.

### Use `providers.kilo`, not the built-in `kilocode` provider

Hermes ships a `kilocode` provider (`hermes_cli/auth.py`, `https://api.kilo.ai/api/gateway`)
and it **hangs**: a turn produced no output in 280s and the pooled credential still read
`request_count: 0`, so hermes never issued the HTTP call. The same prompt through a custom
provider answers. Declare it under `providers:` like `altalt` and `llama-local`:

```yaml
  kilo:
    api: https://api.kilo.ai/api/gateway/v1
    name: kilo
    models:
      nex-agi/nex-n2.5-pro:free: {context_length: 262144}
      nvidia/nemotron-3-ultra-550b-a55b:free: {context_length: 262144}
    default_model: nex-agi/nex-n2.5-pro:free
    extra_headers:
      Authorization: ''
    transport: chat_completions
```

`Authorization: ''` is the keyless shape, same as `altalt`. A bogus bearer
(`Authorization: Bearer keyless`) also works, but the empty header is the documented
anonymous path.

### Never put `llama-local` in the child chain

`llama-server` runs `--parallel 1` and `/slots` reports one slot. Three children would
serialize on it at 8.57 tok/s, each burning toward `child_timeout_seconds`, and the
parent's own local rung would queue behind them. It stays last in the **parent** chain
only.

### Two traps when repointing the parent

- `hermes config set model <x>` prints "Redirecting bare 'model' to 'model.default'
  (preserving N existing model sub-key(s))" and **keeps the old provider's `base_url`,
  `api_mode` and `context_length`**. After switching provider the requests still go to the
  previous host until `model.base_url` is rewritten. Same for `delegation.base_url`.
- `hermes auth remove <provider> <id>` answers "Suppressed env:NAME - it will not be
  re-seeded even if the variable is re-exported later." That is a one-way door for that
  env var on that host.
- A hermes CLI turn on this host takes **75-150s before it prints anything**, answer
  included. A 90s timeout looks exactly like a hang. Give it 250s before concluding.

### groq is unusable for a kakao turn, and not for the reason it looks

`groq` / `openai/gpt-oss-120b` answers a bare prompt in 0.69s, so a smoke test passes and
tempts you to promote it. The real turn always fails:

```
tools: 19, schema bytes 42,613  +  prompt 9,223  =  body 58,304 bytes
HTTP 413 in 0.2s
"Request too large ... service tier `on_demand` on tokens per minute (TPM):
 Limit 8000, Requested 11687"  ->  "type":"tokens","code":"rate_limit_exceeded"
```

It is a **TPM cap, not a context limit**: the 19 tool schemas alone are ~8.8k tokens, so
the request is over the 8,000 limit even with an empty conversation. `model.context_length`
cannot help. Groq Dev Tier would; until then keep it out of both chains.

### A 413 does not fall back (hermes v0.21.2)

`agent/error_classifier.py:396` maps HTTP 413 to
`_v(_R.payload_too_large, should_compress=True)` - **`should_fallback` is absent**. Hermes
reads every 413 as "too big for this model, compress and retry on the same model", and
when compression is exhausted it ends the turn at `agent/turn_overflow.py:271`
("Request payload too large (413). Cannot compress further."), which is what the room
sees. The fallback chain is never consulted.

Groq's 413 is really a rate limit (its own body says `rate_limit_exceeded`); had it
answered 429 the chain would have worked, because `_V_RATE_LIMIT` does set
`should_fallback`. **Local defence: never put a provider that expresses rate limits as
413 in `fallback_providers`.** One status code silently disables failover for that rung.

### opencode-free: keyless, separate quota

Hermes ships three OpenCode providers (`hermes_cli/auth.py:229-237`):

```
opencode-zen    https://opencode.ai/zen/v1      OPENCODE_ZEN_API_KEY
opencode-go     https://opencode.ai/zen/go/v1   OPENCODE_GO_API_KEY
opencode-free   https://opencode.ai/zen/v1      keyless
```

`opencode-free` needs **no key** and its quota is independent of OpenRouter's 50/day, which
is why it carries delegation here. Auth shape is `Authorization: ""` plus attribution
headers (`hermes_cli/models.py` `opencode_zen_free_headers`) - a bearer placeholder 401s.
The relay also wants `x-opencode-session`; hermes adds it (`agent/opencode_affinity.py`)
and it is **cache affinity, not a quota key**, so subagents with their own session ids
spread across backends rather than contending.

Of the 7 advertised free models only `nemotron-3-ultra-free` survives a real turn:
`mimo-v2.5-free` and `deepseek-v4-flash-free` 413 on the payload, the two `muse-spark`
entries 500, `deepseek-v4-flash-free` also reports "Model is unavailable". Load is not the
constraint - 4 concurrent and 8 sequential requests all returned 200 with no throttling -
**queue latency is**: 40-74s even for "1+1?".

### Measuring a provider: do not use bare `python-urllib`

Its default User-Agent trips Cloudflare's bot filter and returns `403 error code 1010` on
api.groq.com, api.altalt.io and opencode.ai. That looks exactly like "the provider is
blocked from this host" and is not - curl, or urllib with any normal UA, gets through.
This cost two wrong conclusions in one session, including removing two live rungs from the
chain. Confirm a provider is dead with curl before believing it.

### Delegation config traps

- `delegation.model` / `delegation.provider` must be explicit strings. The literal `auto`
  kills every subagent with `401 Model auto is not supported` (upstream #84007); empty
  string is the "inherit parent" value.
- `delegation` has no fallback chain of its own unless you set
  `delegation.fallback_providers` (upstream #94629 still open). Without it a single 429
  ends the child.

## DGX vision route (2026-09-14, measured)

The Cloud Vision Bridge section above is the **Mac era** (all five profiles, Google primary).
It no longer describes any live host. On the DGX the primary chat model `zai` /
`glm-4.7-flash` is **text-only**, so every image takes the `vision_analyze` ->
`auxiliary.vision` hop; there is no native attach path.

The inbound half was already wired and needed no change: `kakao_ai_chat.py` downloads a
photo into `MEDIA_DIR`, renders it as a `[사진] file=/absolute/path` line, the prompt
template names `vision_analyze` explicitly, and `vision,video` are both in the default
`toolsets` string.

### `auxiliary.vision.api_key` is load-bearing, even for a keyless endpoint

`check_vision_requirements()` (`tools/vision_tools.py:800`) returns True only when
`resolve_vision_provider_client()` hands back a client. A custom provider with no
resolvable key returns `None`, the check returns False, and **`vision_analyze` is dropped
from the tool list for every turn**. Pointing the route at a local llama.cpp — which wants
no key — silently triggers this.

What reaches the room is not "the tool failed". It is the model answering *"that tool is
not registered in this session"*, or emitting a **fake tool call as body text**:

```json
{"tool": "vision_analyze", "arguments": {"path": "/home/bobeenlee/.hermes/cache/images/x.png"}}
```

Both read as hallucination and send you after the model. They are literally true: the tool
was not in the request. The only trace is one line at daemon level:

```text
check_fn check_vision_requirements returned False; dependent tools will be unavailable this turn
```

A dummy key clears it. The working shape:

```yaml
auxiliary:
  vision:
    provider: custom:llama-local
    model: /home/bobeenlee/models/qwen3.8-27b/Qwen3.8-27B-UD-Q6_K_XL.gguf
    base_url: http://127.0.0.1:8080/v1
    api_key: local          # placeholder; llama.cpp ignores it, the gate does not
    timeout: 120
```

Measure the gate with `skip_tool_search_assembly=False`. The `True` form used to prove a
toolset is present hides `check_fn` failures too, so it reports a tool that no turn will
ever see:

```bash
HERMES_GATEWAY_SESSION=1 ~/.hermes/hermes-agent/venv/bin/python -c '
import sys; sys.path.insert(0,"/home/bobeenlee/.hermes/hermes-agent")
from tools.vision_tools import check_vision_requirements
print("check:", check_vision_requirements())
from model_tools import get_tool_definitions
n=[x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=["vision"],
   disabled_toolsets=[],quiet_mode=True,skip_tool_search_assembly=False)]
print("vision_analyze:", "vision_analyze" in n)'
```

### llama-local already serves the projector

`models/qwen3.8-27b/mmproj-F16.gguf` sits next to the GGUF and the running server reports
it, so the vision backend costs nothing extra to stand up:

```bash
curl -s http://127.0.0.1:8080/v1/models   # -> "capabilities":["completion","multimodal"]
```

| image | `vision_analyze` wall clock |
|---|---|
| 960x544 PNG | 45-57s |
| 4032x2284 JPEG | 66s |

Both are inside the default `timeout: 120`. Large phone photos are downscaled before the
call, so the 4K number is the realistic ceiling rather than an outlier.

End to end on the live KakaoTalk prompt shape: default model **2/2** accurate (it read
footprints in the sand off a 960x544 frame), `custom:llama-local` as primary **1/1**.
Cost is **4-5 minutes per image turn** — the same GPU runs the chat model and the vision
call in series. That is inside the detached worker's cap but it is not interactive.

### Every cloud vision provider on this host was dead the same day

Checked 2026-09-14, which is why the route moved local rather than to another key:

| provider | result |
|---|---|
| `gemini` / `gemini-3.6-flash` | `429 RESOURCE_EXHAUSTED` — "Your prepayment credits are depleted". The key is fine; `GET /v1beta/models` still returns 200 |
| `openrouter` free vision | `429 free-models-per-day`, 50/50 used, resets 00:00 UTC |
| `groq` / `qwen/qwen3.6-27b` | not a VLM. Groq's model list carries **no** vision model at all, so this rung could never have answered |
| `zai` / `glm-4.6v`, `glm-5v-turbo` | `1113 Insufficient balance`. Only `glm-4.7-flash` is free, and it is text-only |

`glm-4.7-flash` itself is intermittent under load — three back-to-back probes returned
200/429/429 (`1305` overloaded, `1302` rate limit). When it is throttled the turn is
answered by the fallback chain, and a fallback answering an image prompt **invents from the
filename**: `comfyui_1789351131972.png` came back as "a ComfyUI workflow diagram" when the
frame was a lighthouse at sunset. Before trusting an image answer, establish which model
produced it.

Backup taken before the change: `~/.hermes/config.yaml.bak-vision-20260914162823`. No
gateway restart is needed — the config cache keys on the file's mtime and size.

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
