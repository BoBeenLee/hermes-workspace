# DGX Spark Laguna S 2.1 llama.cpp Installation

- Task type: `ops-change`
- HIL status: `skipped` (direct Codex request, not Discord)
- Target: `bobeenlee@aitopatom-36a9` through Tailscale SSH
- Branch/worktree: `none` for remote operations; local documentation updated in the current checkout
- Completion mode: `review-required`
- Source ledger: `research/sources/2026-07-26-laguna-s-2.1-dgx.jsonl`

## Requested Outcome

Install Poolside Laguna S 2.1 Q4_K_M and its DFlash draft model on the DGX Spark, serve it through the existing loopback-only llama.cpp slot, register it in `dgx-ai-control`, benchmark baseline versus DFlash, and restore the pre-task `gemma4`/stopped/disabled service state.

## Remote Changes

- Preserved the existing `/home/bobeenlee/src/llama.cpp` build.
- Added isolated Poolside source at `/home/bobeenlee/src/llama.cpp-poolside-laguna`, pinned to upstream commit `04b2b72cb54048ead292884adbe11f284e3ec950`.
- Built CUDA Release binaries for the NVIDIA GB10 with CUDA architecture `121a`.
- Applied a local one-line `<cmath>` include to `common/speculative.cpp`; the pinned Poolside commit uses `std::isfinite` without including the required standard header.
- Extended `/home/bobeenlee/src/dgx-ai-control/dgx_ai_control.py` with an optional per-model `server_bin` setting. Existing models continue to use the original llama.cpp binary.
- Backup directory: `/home/bobeenlee/.config/dgx-ai-control/backups/laguna-20260726-070422`

## Model Configuration

- Main model: `/home/bobeenlee/models/laguna-s-2.1/laguna-s-2.1-Q4_K_M.gguf`
- Draft model: `/home/bobeenlee/models/laguna-s-2.1/laguna-s-2.1-DFlash-BF16.gguf`
- Context: `262144`
- Parallel slots: `1`
- GPU offload: all layers
- KV cache: Q8_0 for K and V
- Network: `127.0.0.1:8080`
- Chat: Jinja with thinking enabled and reasoning preserved
- Speculative decoding: DFlash, block size `16`, `--spec-draft-n-max 15`

## Verification

- Poolside `llama-server` build: `b1-04b2b72`
- Device enumeration: `CUDA0: NVIDIA GB10`
- Isolated binary smoke test: loaded the existing Gemma GGUF on `127.0.0.1:18080`; `/health`, `/props`, and `/v1/models` passed.
- Main GGUF: `68248760064` bytes; SHA-256 `a34c74e46688122bef83122f4133031bababbefcf57436dde97048c91e2cc6ff`
- DFlash GGUF: `2233764224` bytes; SHA-256 `2ee8aa30338d6599bc7a8ce008cc57c56f2c2b2fdc21f6db9ecda203c751bfd4`
- Cold Laguna load: `266s`; one `262144`-token slot; model API, health, props, and loopback binding passed.
- Functional checks: thinking on/off, code generation, tool call, tool-result follow-up, and preserved reasoning passed. No `</assistant>` leakage or parser errors were observed.
- Baseline benchmark, three fixed 256-token coding completions: median `9.699s`, `26.74 tok/s`.
- DFlash benchmark, same workload: median `6.867s`, `38.09 tok/s`; latency improved by `29.2%`, so DFlash remains enabled.
- DFlash draft acceptance for the coding runs was approximately `31.8%` to `42.4%`.
- Initial loading populated about `1.3GiB` of swap transiently. Post-load `vmstat` showed no sustained swap I/O; no OOM or service restart occurred, and approximately `42GiB` remained available while DFlash was loaded.
- Regression: Gemma and Qwen registry entries remained `ready` and continued to resolve through the original llama.cpp binary.
- Final state: `gemma4` selected, `llama-local.service` inactive and disabled, port `8080` closed.

## Checks Run

```text
sha256sum --check
llama-server --version
llama-server --list-devices
GET /health
GET /props
GET /v1/models
POST /v1/chat/completions
dgx-ai-control models
dgx-ai-control current-model
systemctl --user status llama-local.service
ss -ltnp
vmstat 1 5
python3 scripts/hermes/validate_okf.py
git diff --check
```
