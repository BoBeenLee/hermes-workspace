---
type: Tool
title: Free Media Generation Services
description: Measured inventory of no-cost hosted image and video generation backends, and how they attach to the Hermes image_gen / video_gen provider slots.
resource: repo://hermes-workspace/knowledge/tools/free-media-generation-services.md
tags: [hermes, image-gen, video-gen, providers, cloudflare, huggingface]
timestamp: 2026-09-16T13:00:00+09:00
---

# Free Media Generation Services

This document records which hosted image and video generation backends are actually free, what each one costs in its own currency, and where each one plugs into Hermes. Every number below was measured from the DGX host on 2026-09-16, not read off a vendor page. Marketing copy for "free AI video API" is dominated by SEO content farms; the entries here are the ones that survived a real call.

Use this before adding a generation backend, and before concluding that a capability is missing.

## The Slot Shape

`image_generate` and `video_generate` are **provider slots**, not tools to be written. A user plugin calls `ctx.register_image_gen_provider(...)` or `ctx.register_video_gen_provider(...)` and the core tool turns on. Do not write a new tool or an MCP server for this.

Registration is many, selection is one. The DGX already has ten image providers registered (`comfyui`, `deepinfra`, `fal`, `krea`, `meta-ai`, `nous`, `openai`, `openai-codex`, `openrouter`, `xai`) and `get_active_provider()` returns exactly one, chosen by `image_gen.provider` in `config.yaml`. A configured provider is returned **even when `is_available()` is False** — deliberately, so the dispatcher can say "X_API_KEY is not set" instead of silently switching backends. There is no runtime fallback chain, and the model cannot pick a provider: `image_generate` has no `provider` argument.

Two consequences:

- Multi-backend behavior must live **inside one provider**. A provider that wants a fallback ring implements it itself (`plugins/hf_video` does this across Spaces).
- For a plugin provider, capabilities are **per provider, not per model**. `_active_image_capabilities()` calls `provider.capabilities()` once and never consults `list_models()`; only the in-tree FAL path varies capabilities per model. So a provider exposing both a text-only route and a multi-reference route advertises the union for both, and must validate the request shape itself.

The schema is generated from that one capabilities dict. `modalities: ["text", "image"]` adds `image_url`; `max_reference_images > 1` additionally adds `reference_image_urls` with a matching `maxItems`. Declaring a capability the provider cannot honor costs a retry loop every time the model uses it — declare only what a route actually does.

`video_gen` is in `_DEFAULT_OFF_TOOLSETS`, so it needs adding to `toolsets:` in `config.yaml`. For the KakaoTalk daemon, add a `toolsets` key to its `config.json`: `load_config()` is `dict(DEFAULT_CONFIG)` plus `.update()`, so the key overrides the script's built-in string without touching the daemon.

## Video: Hugging Face ZeroGPU Spaces

The only free hosted video generation with a real API. Wired up as `plugins/hf_video` (provider name `hfspace`).

Every Gradio Space on the Hub is also an API endpoint — POST a positional argument array, read the result off an SSE stream. `gradio_client` is not needed. The argument array is unnamed, so **its order is the contract**; `/gradio_api/info` is the source of truth and `space.check_param_order()` re-checks it without spending quota.

Measured: `Lightricks/LTX-2-3` produced 1280x704 / 24fps / 3.04s h264+AAC in 45-63 seconds. Audio is generated alongside the video and cannot be switched off.

The budget is **GPU-seconds per day**, not requests: 2 minutes unauthenticated, 5 with a free account token, 40 on PRO, extensible at $1 per 10 minutes. A 3-second clip costs roughly 45-63 seconds of that, so a free account is 5-7 clips a day and duration is the dial that empties it. Check the tier with `whoami-v2`'s `isPro` field; inferring it from `periodEnd` gives the wrong answer.

Quota exhaustion is indistinguishable from a crashed Space by content — both return `event: error` with `data: null` and no reason. What separates them is the clock: a real render takes ~45s, a quota refusal ~2s because no GPU is ever scheduled. The allowance is per identity, not per Space, so a quota refusal must **not** roll onto another Space; only a 503 should.

## Image: Cloudflare Workers AI

Ten text-to-image models, `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` already present on the DGX, and the free allowance is 10,000 neurons a day. Per-request cost comes back in the `cf-ai-neurons` response header, which is how the table below was measured rather than computed.

| Model | Time | Neurons | Per day |
|---|---|---|---|
| `@cf/bytedance/stable-diffusion-xl-lightning` | 3.8-10.9s | 0.00 | unmetered |
| `@cf/stabilityai/stable-diffusion-xl-base-1.0` | 11.0s | 0.00 | unmetered |
| `@cf/lykon/dreamshaper-8-lcm` | 3.4s | 0 | unmetered |
| `@cf/black-forest-labs/flux-1-schnell` | 2.1s | 172.80 | ~57 |
| `@cf/leonardo/lucid-origin` | 5.0s | 636/tile (docs) | ~3 |
| `@cf/leonardo/phoenix-1.0` | not run | 530/tile (docs) | ~4 |

The three Stable Diffusion models report **zero neurons** and are absent from the pricing page: the daily budget constrains only the FLUX and Leonardo families. That makes Cloudflare the right home for ordinary text-to-image, since it does not touch the Hugging Face allowance at all.

Two call-shape traps. Response format differs by model — `flux-1-schnell` and `lucid-origin` return JSON with base64 in `result.image`, while the Stable Diffusion models return **raw image bytes**. And the FLUX.2 family rejects `{"prompt": ...}` with `required properties at '/' are 'multipart'`; its Workers AI schema is an opaque `{multipart: {body, contentType}}` pass-through to the partner API.

**FLUX.2 reference images are not reachable through that binding as tested.** Four shapes were tried on `flux-2-klein-4b` — `input_image` as a base64 form field, `input_image` plus `input_image_2`, and `input_image` as a file part, all using Black Forest Labs' own documented field names — and every call returned 200 with an identical **104.20 neurons**. Pricing charges 5.37 neurons per input 512x512 tile, so a reference image that was actually read would have raised the number. It did not, so the images were ignored. Guessing further field names is not worth it; a Cloudflare-authored flux-2 example would settle it.

## Image With References: Hugging Face Spaces

Free multi-reference editing exists, on ZeroGPU rather than Cloudflare. Endpoint signatures read from `/gradio_api/info`, which costs no quota:

| Space | Endpoint | Image input |
|---|---|---|
| `Qwen/Qwen-Image-Edit-2509` | `/infer` | `images` as a **list** — true N images |
| `OmniGen2/OmniGen2` | `/run` | `image_input_1` / `_2` / `_3` |
| `black-forest-labs/FLUX.1-Kontext-Dev` | `/infer` | `input_image` — one |

**Image editing and video generation share the same daily ZeroGPU allowance.** Editing is cheaper per call than video, so the clip count is higher, but it is one pool: a day of video testing leaves nothing for image editing. This is the argument for routing plain text-to-image to Cloudflare and spending the Hugging Face allowance only on the shapes that need references.

## Dead Ends (measured, do not re-research)

| Candidate | Result |
|---|---|
| BigModel `cogvideox-flash`, `cogview-3-flash` | Listed as free in the current docs, **both retired**. `1211 模型不存在` on `open.bigmodel.cn` and `api.z.ai`. Zhipu's free *text* models still answer. Probe a model name for free by sending an invalid parameter: model validation runs first, so `1214` means the model exists and `1211` means it does not |
| BigModel registration | `bigmodel.cn/login` offers `+86` only, no country selector and no email tab |
| Gemini image models | `gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-3.1-flash-image` all exist, but the DGX key returns `429 Your prepayment credits are depleted` — this project is not on a free tier |
| Gemini / Veo video | Video generation is paid-tier only on the Gemini API |
| Cloudflare video | The catalog has no video generation model of any kind |
| ModelScope free inference | `/v1/models` carries 37 entries with zero video models; needs an Alibaba Cloud binding |
| Pollinations | `403` (error 1010, bot block) from the DGX; no video subdomain; one image model (`sana`) |
| OpenRouter | Eleven image-output models, none priced at zero |
| HF Inference Providers credits | $0.10 a month free, $2.00 on PRO |
| Alibaba Model Studio (Singapore) | Per-model free quota, but one-time and **90 days**; video quota amounts appear only in the console |
| xAI | `grok-imagine-video` $0.05/sec, `-1.5` $0.08/sec. No free tier in the official docs; the "$25 signup / $175 monthly" figures circulating are not in them |

## Open Items

- Cloudflare is not wired to a provider yet; only the calls above were made. Local ComfyUI Krea2 remains the configured image provider (9s warm, free, unmodelled by any quota).
- `comfyui` declares `{"modalities": ["text"], "max_reference_images": 0}`, so this host currently advertises "text-to-image only" and cannot take a reference image at all.
- The FLUX.2 multipart contract is unresolved.
