# ADR-031: Blackwell Image Default + 131k Context

**Status:** Accepted
**Date:** 2026-03-15
**Wave:** 18

## Decision

Default the LLM Docker image to a locally-built Blackwell-native build (`local/llama.cpp:server-cuda-blackwell`) and raise the context default to 131,072 tokens.

## Context

FormicOS runs the same model (Qwen3-30B-A3B Q4_K_M) on the same hardware (RTX 5090, 32 GB VRAM) as the operator's anyloom stack. The anyloom stack holds 131k context. FormicOS auto-sizes to 16k.

The difference is the Docker image. The official `ghcr.io/ggml-org/llama.cpp:server-cuda` ships CUDA 12.4, which predates Blackwell. The RTX 5090 falls back to PTX JIT, resulting in ~3-4 tok/s instead of ~50-60 tok/s and significantly higher VRAM overhead from unoptimized kernel dispatch. The `--fit on` flag auto-sizes the KV cache to available VRAM, so the extra VRAM overhead directly reduces effective context.

The Blackwell image builds llama.cpp with CUDA 12.8 and native sm_120 kernels, eliminating PTX JIT overhead. This is proven stable on the operator's hardware at 131k context with 2 slots.

## Build Path

`scripts/build_llm_image.sh` (ported from anyloom) clones llama.cpp, builds with:
- CUDA 12.8 + sm_120 (Blackwell native)
- `GGML_CUDA_NO_PINNED=1` (GDDR7 pinned-memory fix)
- `GGML_CUDA_FORCE_CUBLAS=ON` (prompt processing fix)
- `GGML_CUDA_FA_ALL_QUANTS=ON` (sub-f16 KV cache with flash attention)
- `GGML_CUDA_GRAPHS=ON` (kernel launch batching)
- `GGML_FLASH_ATTN=ON` (flash attention kernels)

Build time: ~10-20 minutes. Requires Docker with WSL2 integration.

## Fallback

Operators who haven't built the image set `LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda` in `.env`. The stack falls back to the generic CUDA image with auto-sized (lower) context. The `--fit on` flag prevents OOM in both cases.

## Context Assembly Budget Scaling

At 131k context, the assembly budget scales from 8,000 → 52,000 tokens using the formula `min(effective_ctx × 0.4, 65536)`. Tier budgets scale proportionally.

## Consequences

- Local inference moves from ~16k effective to ~131k effective context
- Token throughput increases from ~3-4 tok/s to ~50-60 tok/s on RTX 5090
- Colonies can use significantly richer context (skills, summaries, workspace docs)
- New operator step: run `bash scripts/build_llm_image.sh` once before first `docker compose up`
- Operators on non-Blackwell GPUs must set `LLM_IMAGE` to the generic image

## Rejected Alternatives

**Keep generic CUDA image as default, document Blackwell as optional**
Rejected. FormicOS is built for RTX 5090. Defaulting to an image that delivers 10× worse performance on the target hardware is a bad default. Operators on other GPUs override `LLM_IMAGE`.

**Wait for official Blackwell support in upstream llama.cpp images**
Rejected. The upstream image ships CUDA 12.4 with no Blackwell-native kernels. A local build is the proven path and adds ~15 minutes of one-time setup.

**Target 65k as a conservative midpoint**
Rejected. 131k is validated on the target hardware. `--fit on` auto-sizes down if VRAM is tighter than expected. There is no benefit to a conservative midpoint when the floor is dynamic.

## Implementation Note

See `docs/waves/wave_18/algorithms.md`, §3.
