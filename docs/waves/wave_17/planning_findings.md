# Wave 17 Planning Findings — Repo Audit

**Date:** 2026-03-15
**Auditor:** Planning pass against live repo (post-Wave 16)
**Scope:** Truth, control, safe evolution, local-runtime optimization

---

## 1. Critical Correction: CONFIG_UPDATE Is NOT a Live Queen Capability

The INSIGHTS.md from the prealpha lessons states: *"The alpha's Queen emits CONFIG_UPDATE directives via queen_runtime.py. If the LLM hallucinates a bad payload, the colony manager applies it unvalidated."*

**This is false for the live alpha.** The Queen (`surface/queen_runtime.py`) has exactly three tools:

- `spawn_colony` — spawns a worker colony
- `get_status` — reads workspace state
- `kill_colony` — cancels a running colony

There is no CONFIG_UPDATE tool. The Queen cannot mutate configuration. The `update_config` WS command in `surface/commands.py` is an operator-facing workspace config mutator (model assignments, strategy, budget) that routes through `config_endpoints.py`. It is not Queen-driven.

**Impact on Wave 17:** The config validator is preventive infrastructure — required before adding CONFIG_UPDATE as a Queen tool, not a fix for a live vulnerability. The validator and the Queen tool should ship together.

---

## 2. Dead Telemetry Paths in the Local Model Snapshot

Wave 16 already corrected two adjacent truth seams:

- Cloud endpoint `no_key` status is now derived from actual key presence rather than static configured status
- Local context window can now follow live probe/config instead of a separate stale hardcoded value

The remaining dead path is narrower but still operator-visible: local GPU/slot telemetry is only partially real.

The `ws_handler.py` `_probe_local_endpoints()` method queries llama.cpp's `/health` and `/props` endpoints. It then reads several fields that llama.cpp does not provide:

| Field | Code | llama.cpp Reality | Result |
|-------|------|-------------------|--------|
| `vram` | `probe.get("vram", -1)` | `/props` has no `vram` field | **Always -1** |
| `gpu` | `probe.get("gpu", "")` | `/props` has no `gpu` field | **Always ""** |
| `quant` | `probe.get("quant", "")` | `/props` has no `quant` field | **Always ""** |
| `slots_idle` | `probe.get("slots_idle", 0)` | `/health` returns this | **Works** |
| `slots_processing` | `probe.get("slots_processing", 0)` | `/health` returns this | **Works** |
| `n_ctx` | via `_derive_context_window()` | `/props` → `default_generation_settings.n_ctx` | **Works** |
| `total_slots` | Not read | `/props` returns this | **Available but unused** |

The `view_state.py` `_build_local_models()` function maps these into the `LocalModel` shape expected by the frontend `types.ts`. Three of its six data fields are always phantom values.

**The frontend `LocalModel` interface defines:**
```typescript
interface LocalModel {
  id: string;       // ✅ from config
  name: string;     // ✅ from config
  quant: string;    // ❌ always ""
  status: string;   // ✅ derived from probe + config
  vram: number;     // ❌ always -1
  ctx: number;      // ✅ from /props
  maxCtx: number;   // ✅ from /props
  backend: string;  // ✅ from config
  gpu: string;      // ❌ always ""
  slots: number;    // ✅ from /health
  provider: string; // ✅ from config
}
```

**Fix path:** llama.cpp does not expose GPU VRAM via any REST endpoint. The achievable telemetry is:

1. **Slot utilization** — already works via `/health` (`slots_idle`, `slots_processing`)
2. **Context window** — already works via `/props` (`default_generation_settings.n_ctx`)
3. **Per-slot context usage** — available via `/health?include_slots` parameter (NOT currently probed)
4. **Total slots** — available via `/props` (`total_slots`) but not read
5. **GPU VRAM** — requires either `nvidia-smi` exec inside the container or the `--metrics` Prometheus endpoint. Neither is wired today.

Given the operator's current priority, Wave 17 should treat real VRAM monitoring as an explicit target to evaluate and land if practical on the current stack, not as a casual default defer. Honest unavailability is still better than fake numbers, but the planning default should bias toward a concrete probe path.

---

## 3. Model Policy Editing — Appears Wired End-to-End

`app.py` exposes `PATCH /api/v1/models/{address}` → `update_model_policy()`. It:
- Accepts `max_output_tokens`, `time_multiplier`, `tool_call_multiplier`
- Validates via Pydantic `model_copy(update=...)`
- Applies in-memory to `settings.models.registry`
- Persists to `config/formicos.yaml` via `save_model_registry()`

The frontend `model-registry.ts` has matching state: `editMaxOutput`, `editTimeMul`, `editToolMul`. This path appears complete but needs a smoke trace to confirm the full round-trip (edit → save → page refresh → values persist).

---

## 4. Caste Recipe Editing — Wired End-to-End

`app.py` exposes `PUT /api/v1/castes/{caste_id}` → `upsert_caste()`. It validates a `CasteRecipe`, updates the in-memory `CasteRecipeSet`, persists to YAML via `save_castes()`, and updates both `runtime.castes` and `ws_manager._castes`. The frontend `caste-editor.ts` consumes this. This path appears complete.

---

## 5. Provider Cooldown — In-Memory Only, No Operator Visibility

ADR-024 describes a cooldown cache in `LLMRouter` (`surface/runtime.py`). Cooldown state is in-memory. When a provider is cooled down, routing falls back to the next viable option. Colony chat messages log fallback events. But there is no snapshot field exposing cooldown state to the frontend — the operator sees "connected" for a cooled-down provider.

---

## 6. Docker Compose — Live vs Prealpha vs Operator's Known-Good (anyloom)

The live compose is conservative compared to what the RTX 5090 can actually handle. The operator's own anyloom stack runs 131k context on the same hardware. Three-way comparison:

| Setting | Live FormicOS | Prealpha | Operator anyloom | Notes |
|---------|---------------|----------|------------------|-------|
| Context size | 8192 | 8192 | **131072** | Live is drastically underutilizing the GPU |
| `--flash-attn` | on | on | on | Same |
| `--fit` | **missing** | missing | **on** | Automatically sizes KV cache to available VRAM |
| `--cache-type-k/v` | q8_0 | q8_0 | q8_0 | Same |
| `-np` (slots) | 2 | 2 | 2 | Same |
| `-sps` (slot prompt similarity) | **missing** | missing | **0.5** | Better slot reuse for shared prefixes |
| `--batch-size` | 4096 | 4096 | **8192** | Double throughput on prompt processing |
| `--ubatch-size` | 2048 | 2048 | **4096** | Double micro-batch throughput |
| `--cache-ram` | ❌ missing | 1024 | missing | Free prompt cache in system RAM |
| `--reasoning-format` | missing | missing | **none** | Suppresses think-token overhead for non-reasoning tasks |
| `GGML_CUDA_GRAPH_OPT` | missing | missing | **1** | CUDA graph optimization for faster inference |
| `ipc: host` | missing | missing | **yes** | Shared memory for CUDA IPC, reduces overhead |
| `--jinja` | yes | yes | yes | Same |
| `--threads / --threads-batch` | 8 / 16 | 8 / 16 | 8 / 16 | Same |
| `--slots` flag | yes | yes (implied) | yes | Same |
| LLM image | official CUDA | official CUDA | **custom Blackwell** | Custom build avoids PTX JIT penalty on RTX 5090 |
| Embed model | GPU (Qwen3-Embed, ~700MB) | CPU (BGE-M3) | GPU (BGE-M3, ~635MB) | Different model choices |
| Embed context | unspecified | 8192 | **16384** (/2 slots = 8192/slot) | anyloom documents the math |

**Key takeaway:** The live FormicOS compose is leaving massive performance on the table. The same hardware handles 131k context in the anyloom stack. The 8192 default was inherited from early development; the RTX 5090 with Qwen3-30B-A3B Q4_K_M and `--fit on` can handle dramatically more.

**What Wave 17 should carry forward from anyloom:**
- `--fit on` — lets llama.cpp auto-size KV cache to available VRAM (safeguards against OOM)
- `GGML_CUDA_GRAPH_OPT=1` — free inference speedup
- `--batch-size 8192` / `--ubatch-size 4096` — double prompt processing throughput
- `-sps 0.5` — better slot prefix reuse for multi-agent workloads
- `--cache-ram 1024` — prompt cache (from prealpha, not in anyloom but compatible)
- `--reasoning-format none` — suppress think-token overhead for standard agent tasks
- `ipc: host` — reduce CUDA IPC overhead

**What to evaluate but not auto-port:**
- Context size bump (8192 → much higher, gated on real VRAM telemetry from A1)
- Custom Blackwell image (requires operator build script infrastructure)

---

## 7. Lifespan Integration Points

The `app.py` lifespan is a clean `@asynccontextmanager`:

```python
async with lifespan(_app):
    # 1. Replay events into projections
    # 2. First-run bootstrap (if empty)
    # 3. Colony rehydration
    yield
    # 4. event_store.close()
```

The telemetry bus integrates cleanly: `bus.start()` after replay, `bus.stop()` before store close. No architectural blockers.

---

## 8. Event Contract Status

Wave 16 pushed the event union from 35 → 36 (`ThreadRenamed`). The union is closed — additions require operator approval per CLAUDE.md constraint #5. Core Wave 17 scope (validator, telemetry bus, local optimization, truth audit) requires **zero new events**. The telemetry bus explicitly avoids polluting the domain event stream.

If the hypothesis tracker stretch goal is included: +2 events (`HypothesisProposed`, `HypothesisResolved`), union goes 36 → 38.

---

## 9. LOC Budget Status

CLAUDE.md specifies a ≤15K LOC hard limit on `core/ + engine/ + adapters/ + surface/`. Current: ~6,500 Python LOC. Wave 17 additions (config validator ~150 LOC, telemetry bus ~120 LOC, probe improvements ~50 LOC) add ~320 LOC. Well within budget.

---

## 10. Frontend Component Inventory

21 Lit Web Components, ~3,400 LOC. The model-registry component is the primary surface for Wave 17 truth improvements. No new components needed — only data wiring fixes in `model-registry.ts` and `view_state.py`.
