# Wave 17 Plan — Runtime Truth + Safe Evolution + Local Optimization

**Wave:** 17 — "Nothing Lies"
**Theme:** Every display is truthful. Every control works. Every mutation is validated. Local inference is tuned.
**Contract changes:** 0 events (stretch: +2 for hypothesis tracker). Event union stays at 36 (stretch: 38). Ports frozen.
**Estimated LOC delta:** ~320 Python, ~80 TypeScript

---

## Wave 17 Is a Hardening Wave

Wave 16 delivered operator control surfaces (rename, playbook, file I/O, model/caste editing). Wave 17 ensures those surfaces are truthful and adds the minimum guardrails for safe Queen evolution.

Wave 17 is NOT a feature wave. No new views, no new colony mechanics, no new protocols. The acceptance test is: every number the operator sees is real, every button does something, and the system is ready for the Queen to start mutating configuration safely.

---

## Tracks

Three parallel tracks. Track D is a stretch goal.

### Track A — Truth & Telemetry

**Goal:** Every operator-visible metric reflects reality. Dead telemetry paths are either fixed or removed.

**A1. Fix local model snapshot fields.**
The `view_state.py` `_build_local_models()` function populates `vram`, `gpu`, and `quant` from llama.cpp `/props`, but llama.cpp does not return these fields. They are always -1 or empty. This is a wired-but-empty path — exactly the failure mode the prealpha died from.

Fix: Replace phantom fields with data llama.cpp actually provides. Probe `/health?include_slots` for per-slot context utilization. Read `total_slots` from `/props`. For VRAM, choose one concrete real source on the live stack (`nvidia-smi` inside the llm container or a metrics scrape) and land it if practical; only fall back to explicit unavailability if that probe path proves too invasive for this wave. Do not keep fake `-1` or placeholder GPU data in the UI.

Files touched:
- `src/formicos/surface/ws_handler.py` — expand `_probe_local_endpoints()` to read `/health?include_slots` and `total_slots` from `/props`
- `src/formicos/surface/view_state.py` — update `_build_local_models()` to use real slot data
- `frontend/src/types.ts` — adjust `LocalModel` to add `slotsIdle`, `slotsProcessing`, `slotDetails`; keep `vram` only if backed by a real probe, otherwise make the unavailable state explicit
- `frontend/src/components/model-registry.ts` — render truthful slot utilization and truthful VRAM state, suppress phantom fields
- `frontend/src/components/queen-overview.ts` — keep the supercolony VRAM / local-runtime summary truthful
- `frontend/src/components/settings-view.ts` — hide or relabel AG-UI / A2A placeholder protocol status if still inactive
- `frontend/src/components/formicos-app.ts` — protocol-bar compatibility only if the shell-level status pills need the same truth cleanup

**A2. Telemetry bus.**
The alpha has event sourcing for domain events but no separate channel for operational metrics. The telemetry bus provides a bounded async queue with fan-out to sinks, keeping operational telemetry out of the domain event stream. This is the observation backbone for routing decisions, token expenditure, and future metrics.

Files touched:
- `src/formicos/engine/telemetry_bus.py` — new, ~120 LOC, adapted from prealpha `instrumentation_bus.py`
- `src/formicos/surface/app.py` — wire `bus.start()` / `bus.stop()` into lifespan
- `src/formicos/adapters/telemetry_jsonl.py` — new, ~30 LOC, JSONL debug sink
- `src/formicos/engine/runner.py` — emit `routing_decision` and `token_expenditure` events at routing and LLM-call sites

**A3. Provider status freshness.**
Cloud provider `status` is derived at load time and never updated. A cooled-down or crashed provider still shows "connected" in the snapshot. Add a `providerHealth` field to the snapshot that reflects cooldown state from `LLMRouter`.

Files touched:
- `src/formicos/surface/view_state.py` — add provider health to `_build_cloud_endpoints()`
- `src/formicos/surface/runtime.py` — expose cooldown state from `LLMRouter`

**A4. Dead control audit.**
Walk every button, toggle, and input in the 21 Lit components. Verify each one dispatches a command that reaches a handler that produces an effect. Document any dead controls in this wave's smoke results. Fix or remove them.

Concrete targets:
- AG-UI and A2A protocol status: if still placeholder-only, hide them or relabel them as inactive placeholders — do not leave them looking like live indicators
- Any template editing flows that don't persist
- Export button edge cases (empty colonies, no Archivist)

**A5. Data-flow smoke traces (acceptance gate).**
Every new or fixed telemetry path must be verified end-to-end:

1. **Slot utilization trace:** Start LLM container → probe `/health?include_slots` → verify snapshot contains real slot data → verify model-registry.ts renders it
2. **Routing decision trace:** Spawn colony → verify telemetry bus receives `routing_decision` event → verify JSONL sink writes it
3. **Model policy edit trace:** Edit `maxOutputTokens` in UI → verify YAML persistence → restart → verify value survives
4. **Provider health trace:** Verify both truth cases:
   - absent/empty API key → cloud endpoint shows `no_key`
   - invalid non-empty API key → endpoint starts usable, then degrades honestly after a failed call (for example `cooldown` if A3 lands)

---

### Track B — Safe Evolution Primitives

**Goal:** The Queen can be given CONFIG_UPDATE capability in Wave 18 without risk. All guardrails are in place.

**B1. Config validator.**
Pure validation module that prevents hallucinated CONFIG_UPDATE payloads from reaching the context tree. Includes forbidden string scan, recursive depth guard, NaN/Inf rejection, param path whitelist, and type+range enforcement.

The validator ships as preventive infrastructure — it does not fix a live vulnerability (the Queen has no CONFIG_UPDATE tool yet). It is a prerequisite for adding that tool.

Files touched:
- `src/formicos/surface/config_validator.py` — new, ~150 LOC, adapted from prealpha. Update `PARAM_RULES` paths to match live `caste_recipes.yaml` schema (`castes.{name}.{field}`, not `recipes.{name}.{field}`)
- Tests: valid payload, unknown path, out-of-range, forbidden string, NaN/Inf, depth guard, oversized payload

**B2. Experimentable params whitelist.**
Drop-in YAML config file defining which parameters the Queen can mutate, with type and range bounds. The config validator references this.

Files touched:
- `config/experimentable_params.yaml` — new, adapted from prealpha. Update paths from `recipes.*` to `castes.*` to match live schema.

**B3. Sandbox profiles.**
Drop-in YAML config file with the three profiles the alpha needs: `harness` (dev/test), `local_sandboxed` (production default), `queen_sandbox` (Queen elevated). Prune the four profiles the alpha doesn't need (peer_strict, wan_maximum, local_trusted, sandboxed duplicate).

Files touched:
- `config/sandbox_profiles.yaml` — new, pruned from prealpha

**B4. FORBIDDEN_CONFIG_PATHS deny-list.**
Security-critical paths the Queen can never mutate (auth, API keys, ports, database, MCP server definitions, workspace roots). Second defense layer on top of the whitelist.

Files touched:
- `src/formicos/surface/config_validator.py` — add `FORBIDDEN_CONFIG_PREFIXES` set

---

### Track C — Local Runtime Optimization + Frontend Wiring

**Goal:** The local Qwen/llama.cpp stack utilizes the RTX 5090 properly, and the frontend displays truthful inference metrics.

**Context:** The operator's own anyloom stack runs **131k context** on the same RTX 5090 with Qwen3-30B-A3B Q4_K_M. The current FormicOS default of 8192 is drastically underutilizing the hardware. The anyloom compose demonstrates that `--fit on`, `GGML_CUDA_GRAPH_OPT=1`, larger batch sizes, `-sps 0.5`, and `--reasoning-format none` all work in production on this GPU. See `planning_findings.md` §6 for the full three-way comparison.

**C1. Docker compose improvements.**
Carry forward the proven flags from the anyloom reference config:

- `--cache-ram ${LLM_CACHE_RAM:-1024}` — prompt caching in system RAM (free performance)
- `--fit on` — auto-size KV cache to available VRAM (prevents OOM, enables higher context)
- `GGML_CUDA_GRAPH_OPT=1` — CUDA graph optimization (free inference speedup)
- `--batch-size 8192` / `--ubatch-size 4096` — double prompt processing throughput
- `-sps ${LLM_SLOT_PROMPT_SIMILARITY:-0.5}` — better slot prefix reuse for multi-agent workloads
- `--reasoning-format none` — suppress think-token overhead for standard agent tasks
- `-np ${LLM_SLOTS:-2}` — parameterize slot count
- `--n-gpu-layers ${EMBED_GPU_LAYERS:-99}` on embed sidecar — CPU fallback option

Files touched:
- `docker-compose.yml` — add all above flags
- `.env.example` — document `LLM_CACHE_RAM`, `LLM_SLOTS`, `LLM_CONTEXT_SIZE`, `LLM_SLOT_PROMPT_SIMILARITY`, `EMBED_GPU_LAYERS` with comments
- `src/formicos/adapters/llm_openai_compatible.py` — remove the hardcoded local concurrency limit or derive it from the same slot/env source so adapter behavior matches `LLM_SLOTS`

**C2. Context size evaluation.**
8192 is tiny for multi-agent workloads. The same GPU handles 131k in the operator's anyloom stack. With `--fit on` guarding against OOM, the risk of a larger default is low.

Evaluation target: bump the default to at least 32768 (4× current), with env override up to 131072. Gate the final default on real VRAM telemetry from A1 if the probe lands, otherwise gate on a manual test run with `--fit on` confirming stability.

If approved, update:
- `docker-compose.yml`: `--ctx-size ${LLM_CONTEXT_SIZE:-32768}` (or higher pending telemetry)
- `config/formicos.yaml`: `context_window` for `llama-cpp/gpt-4` to match
- `config/formicos.yaml`: bump `context.total_budget_tokens` proportionally (4000 → 8000+)

**C3. Embed sidecar CPU fallback.**
Add `${EMBED_GPU_LAYERS:-99}` env var. Setting to 0 moves the Qwen3-Embedding sidecar to CPU, freeing ~700MB VRAM for operators who want more LLM headroom.

Files touched:
- `docker-compose.yml` — parameterize `--n-gpu-layers` on embed sidecar

**C4. Frontend wiring for truthful telemetry.**
Wire the expanded probe data from A1 into model-registry.ts. Display slot utilization (idle/processing/total), context window size, server health status, and real VRAM if the chosen probe path lands. Suppress any remaining phantom fields.

Files touched:
- `frontend/src/types.ts` — adjust `LocalModel` interface
- `frontend/src/components/model-registry.ts` — render slot utilization bar, truthful status indicators

---

### Track D — Hypothesis Tracker (Stretch Goal)

**Prerequisite:** Tracks A and B land cleanly.
**Contract change:** +2 events (`HypothesisProposed`, `HypothesisResolved`). Union 36 → 38.

**D1. Hypothesis types.**
Add `HypothesisStatus` enum and `QueenHypothesis` model to `core/types.py`. Add two new events to `core/events.py`. Update `docs/contracts/events.py` mirror. Update `frontend/src/types.ts`.

**D2. Hypothesis lifecycle.**
Add `surface/hypothesis_tracker.py` with state machine (PROPOSED → EXPERIMENT_EMITTED → CONFIRMED / REFUTED / EXPIRED), rolling-cap storage (200 entries, 3K char budget), and `format_hypothesis_context()` for Queen prompt injection.

**D3. Wire into Queen runtime.**
Extend `queen_runtime.py` to include hypothesis context in the Queen's message history. The Queen reads past hypotheses to avoid re-proposing failed experiments.

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|-----------------|--------------|
| **Coder 1** | A (Truth + Telemetry) | `ws_handler.py`, `view_state.py`, `telemetry_bus.py` | None — starts immediately |
| **Coder 2** | B (Safe Evolution) | `config_validator.py`, config YAMLs | None — starts immediately |
| **Coder 3** | C (Local Runtime + Frontend) | `docker-compose.yml`, `model-registry.ts`, `types.ts` | Rereads `types.ts` and `view_state.py` after Coder 1 lands A1 |

### Serialization Rules

- **Coder 1 lands A1 first** on `view_state.py` and `types.ts` (probe expansion + LocalModel shape change)
- **Coder 3 rereads** `view_state.py` and `types.ts` before doing C4 (frontend wiring)
- **Coder 2 is fully independent** — no overlap with A or C file ownership

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `frontend/src/types.ts` | 1 + 3 | Coder 1 first (LocalModel shape), Coder 3 rereads before wiring |
| `src/formicos/surface/view_state.py` | 1 + 3 | Coder 1 first (probe data), Coder 3 rereads |
| `docker-compose.yml` | 3 only | No overlap |
| `src/formicos/surface/app.py` | 1 only | No overlap (lifespan bus wiring) |
| `src/formicos/adapters/llm_openai_compatible.py` | 3 only | No overlap |

---

## Acceptance Criteria

Wave 17 is complete when:

1. **No phantom telemetry.** Every number in the model registry reflects a real probe value or is explicitly marked unavailable. VRAM is either measured from a concrete source in this wave or clearly surfaced as an unresolved blocker rather than faked.
2. **Config validator passes all safety tests.** Forbidden strings, depth guard, NaN/Inf, unknown paths, range enforcement.
3. **Telemetry bus delivers events.** At least `routing_decision` and `token_expenditure` events flow from runner → bus → JSONL sink.
4. **Local inference properly tuned.** `--cache-ram`, `--fit on`, `GGML_CUDA_GRAPH_OPT`, larger batches, `-sps`, and slot parameterization all active. Context default raised from 8192 pending telemetry confirmation.
5. **No dead controls.** Every button dispatches a command that produces a visible effect, or is removed. AG-UI/A2A placeholders are hidden or honestly relabeled.
6. **4 smoke traces pass.** Slot utilization, routing decision, model policy edit, provider health — all verified end-to-end.
7. **All CI gates green.** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`

---

## Not In Wave 17

| Item | Reason | When |
|------|--------|------|
| Queen CONFIG_UPDATE tool | Validator ships first, tool ships when ready | Wave 18 |
| Full experiment engine / A-B testing | Needs hypothesis tracker + CONFIG_UPDATE | Wave 18+ |
| EvoFlow / NSGA-II genetic optimization | Premature without experiment engine | Post-alpha |
| Routing learner (EMA-based adaptive) | Needs experiment outcome data | Wave 19+ |
| Gap analyzer (knowledge gap → research) | Needs experiment engine to execute | Wave 18+ |
| RAG gating (3-tier confidence) | Skill bank not yet large enough | Wave 19+ |
| Dashboard / new visualization wave | Alpha UI is sufficient | Post-alpha |
| WAN / federation / cross-node | Single-node alpha | Post-alpha |
| Billing / metering / Stripe | Internal cost tracking is sufficient | Post-alpha |
| AG-UI / A2A adapter implementation | Interface-only is sufficient | Wave 19+ |
| Sandbox adapter implementation | Config ships (B3), adapter deferred | Wave 18+ |
| Colony summary model | Cross-colony learning premature | Wave 18+ |
| Custom Blackwell llama.cpp image | Requires build script infrastructure | Wave 18 |
