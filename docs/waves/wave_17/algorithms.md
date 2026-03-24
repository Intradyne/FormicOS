# Wave 17 Algorithms — Implementation Reference

**Wave:** 17 — "Nothing Lies"
**Purpose:** Technical implementation guide for all three tracks. Coder teams should read the section for their track before writing code.

---

## §1. Local Model Probe Expansion (Track A, A1)

### Current Probe Pipeline

```
ws_handler._probe_local_endpoints()
  → GET {endpoint}/health    → slots_idle, slots_processing
  → GET {endpoint}/props     → (attempts vram, gpu, quant — all missing from llama.cpp)
  → view_state._build_local_models()  → LocalModel dict
  → snapshot["localModels"]  → WebSocket → frontend model-registry.ts
```

### llama.cpp Server Endpoints (Verified)

**`GET /health`** returns:
```json
{"status": "ok", "slots_idle": 1, "slots_processing": 1}
```

**`GET /health?include_slots`** returns (requires `--slots` flag, which the live compose already passes):
```json
{
  "status": "ok",
  "slots_idle": 1,
  "slots_processing": 1,
  "slots": [
    {
      "id": 0,
      "state": 1,
      "n_ctx": 8192,
      "n_predict": -1,
      "prompt_tokens": 245,
      "next_token": {"has_next_token": true}
    },
    {
      "id": 1,
      "state": 0,
      "n_ctx": 8192,
      "prompt_tokens": 0,
      "next_token": {"has_next_token": false}
    }
  ]
}
```

Key per-slot fields: `state` (0=idle, 1=processing), `n_ctx` (slot context size), `prompt_tokens` (current prompt tokens cached in slot).

**`GET /props`** returns:
```json
{
  "assistant_name": "",
  "user_name": "",
  "default_generation_settings": {
    "n_ctx": 8192,
    "n_predict": -1,
    "model": "/models/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf",
    "seed": -1,
    "temperature": 0.6,
    "...": "..."
  },
  "total_slots": 2,
  "chat_template": "..."
}
```

Key fields: `total_slots`, `default_generation_settings.n_ctx`, `default_generation_settings.model`.

**NOT available from any llama.cpp REST endpoint:** `vram`, `gpu`, `quant`. These require a second source such as `nvidia-smi` or the `--metrics` Prometheus exporter.

### Expanded Probe Implementation

```python
# In ws_handler._probe_local_endpoints():
# After existing /health probe, add /health?include_slots
try:
    slots_resp = await client.get(f"{ep}/health", params={"include_slots": ""})
    if slots_resp.status_code == 200:
        slots_data = slots_resp.json()
        slot_details = slots_data.get("slots", [])
        result["slot_details"] = [
            {
                "id": s.get("id"),
                "state": s.get("state", 0),  # 0=idle, 1=processing
                "n_ctx": s.get("n_ctx", 0),
                "prompt_tokens": s.get("prompt_tokens", 0),
            }
            for s in slot_details
        ]
except Exception:
    pass  # slot details are optional — degrade gracefully

# From /props, also read total_slots
result["total_slots"] = pdata.get("total_slots", -1)
```

### Updated LocalModel Shape

```typescript
// In frontend/src/types.ts — replace phantom fields with real slot data,
// and keep VRAM only if backed by a concrete probe path.
interface LocalModel {
  id: string;
  name: string;
  status: 'loaded' | 'available' | 'error';
  ctx: number;           // from /props default_generation_settings.n_ctx
  maxCtx: number;        // same as ctx (configured value)
  backend: string;       // provider prefix
  provider: string;
  vram: number | null;   // real GPU VRAM if probed from a concrete source, else null
  slotsTotal: number;    // from /props total_slots
  slotsIdle: number;     // from /health slots_idle
  slotsProcessing: number; // from /health slots_processing
  slotDetails: SlotDetail[] | null;  // from /health?include_slots
}

interface SlotDetail {
  id: number;
  state: number;       // 0=idle, 1=processing
  nCtx: number;        // per-slot context window
  promptTokens: number; // current tokens cached
}
```

Fields removed or deprecated: `gpu` (always ""), `quant` (always ""). `vram` should survive only if backed by a real probe path; otherwise it should be `null` and rendered honestly as unavailable. Do not continue sourcing any of these from phantom `/props` fields.

### VRAM Probe Decision

Wave 17 should evaluate one concrete VRAM source rather than assuming deferral:

1. **`nvidia-smi` inside the llm container** — simplest operator-facing truth if the container/runtime allows it. The `ghcr.io/ggml-org/llama.cpp:server-cuda` image is CUDA-based and likely includes `nvidia-smi`. But the current FormicOS compose does **not** mount a Docker socket into the `formicos` container, so this path is not available “for free.” If Track A chooses it, the wave must explicitly add an access path rather than hand-wave one:
   - mount a Docker socket into `formicos` and call `docker exec formicos-llm nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits`, or
   - add a tiny host-side helper/proxy the app can call safely
2. **Prometheus scrape from llama.cpp `--metrics`** — cleaner default if avoiding Docker-socket access. Add `--metrics` to the compose command and scrape the exposed metrics endpoint over HTTP. This is a better fit for the current architecture if the needed VRAM gauges are present.

If neither path is acceptable in Wave 17, the UI must render VRAM as explicitly unavailable rather than inventing values. But the planning default should be to try to land one real source.

---

## §2. Telemetry Bus (Track A, A2)

### Architecture

```
engine/runner.py ─── emit_nowait() ───→ TelemetryBus (engine/)
                                            │
                                      ┌─────┼─────┐
                                      ▼     ▼     ▼
                                   JSONL  Future  Future
                                   Sink   Sink    Sink
                                (adapters/)
```

The bus lives in `engine/` (imports only core types). Sinks live in `adapters/`. The bus is a singleton, started/stopped in the `app.py` lifespan.

### TelemetryEvent Model

```python
# In engine/telemetry_bus.py
class TelemetryEvent(BaseModel):
    """Single operational telemetry event. Not persisted in the domain event store."""
    model_config = FrozenConfig

    event_type: str          # e.g. "routing_decision", "token_expenditure"
    timestamp: float = Field(default_factory=time.time)
    colony_id: str = ""
    round_num: int = 0
    payload: dict[str, str | int | float | bool] = Field(default_factory=dict)
```

### Bounded Queue Semantics

- Capacity: 10,000 events (configurable)
- Overflow: drop oldest, never block
- Pre-start: events queued in thread-safe deque, migrated to asyncio.Queue on `start()`
- Fan-out: registered async callables. Sink failures caught and logged, never propagated.
- Singleton: `get_telemetry_bus()` returns module-level instance. `reset_telemetry_bus()` for tests.

### Emit Helpers

Wire into `engine/runner.py` at two sites:

```python
# After routing decision (in _resolve_model or equivalent):
get_telemetry_bus().emit_nowait(TelemetryEvent(
    event_type="routing_decision",
    colony_id=colony_context.colony_id,
    round_num=colony_context.round_number,
    payload={
        "caste": agent.caste,
        "phase": phase,
        "selected_model": selected_model,
        "reason": reason,  # "routing_table", "budget_gate", "cascade_default"
    },
))

# After LLM call completes:
get_telemetry_bus().emit_nowait(TelemetryEvent(
    event_type="token_expenditure",
    colony_id=colony_context.colony_id,
    round_num=colony_context.round_number,
    payload={
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost_usd": cost,
    },
))
```

### JSONL Sink

```python
# In adapters/telemetry_jsonl.py
class JSONLSink:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def __call__(self, event: TelemetryEvent) -> None:
        line = event.model_dump_json() + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
```

### Lifespan Wiring

```python
# In app.py lifespan, after replay completes:
from formicos.engine.telemetry_bus import get_telemetry_bus
from formicos.adapters.telemetry_jsonl import JSONLSink

bus = get_telemetry_bus()
bus.add_sink(JSONLSink(data_dir / "telemetry.jsonl"))
await bus.start()
# ... yield ...
await bus.stop()
```

---

## §3. Config Validator (Track B, B1)

### Adaptation from Prealpha

The prealpha validator uses `recipes.{caste}.{field}` paths. The live alpha uses `castes.{name}.{field}` in `caste_recipes.yaml`. The `PARAM_RULES` dict must be updated to match.

### Live Alpha Caste Recipe Schema

From `config/caste_recipes.yaml`, each caste has:
- `name`, `description`, `system_prompt` (string)
- `temperature` (float)
- `max_tokens` (int)
- `tools` (list of strings)
- `max_iterations` (int, Wave 14)
- `max_execution_time_s` (int, Wave 14)
- `base_tool_calls_per_iteration` (int, Wave 14)
- `tier_models` (dict, optional)

### Updated PARAM_RULES

```python
PARAM_RULES: dict[str, dict[str, Any]] = {
    # Temperature — per caste
    "castes.queen.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "castes.coder.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "castes.reviewer.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "castes.researcher.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "castes.archivist.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    # Token limits
    "castes.coder.max_tokens": {"type": "int", "min": 500, "max": 16000},
    "castes.reviewer.max_tokens": {"type": "int", "min": 500, "max": 16000},
    "castes.researcher.max_tokens": {"type": "int", "min": 500, "max": 16000},
    "castes.archivist.max_tokens": {"type": "int", "min": 500, "max": 16000},
    # Iteration caps (Wave 14)
    "castes.coder.max_iterations": {"type": "int", "min": 1, "max": 20},
    "castes.reviewer.max_iterations": {"type": "int", "min": 1, "max": 20},
    # Execution time
    "castes.coder.max_execution_time_s": {"type": "int", "min": 30, "max": 600},
}
```

### FORBIDDEN_CONFIG_PREFIXES

```python
FORBIDDEN_CONFIG_PREFIXES: frozenset[str] = frozenset({
    "system.",           # host, port, data_dir
    "models.registry.",  # API keys, endpoints
    "embedding.",        # model swap
    "vector.",           # Qdrant URL
    "knowledge_graph.",  # DB paths
    "skill_bank.",       # confidence tuning
})
```

These prefixes are checked AFTER the whitelist pass. Even if a path somehow passes the whitelist, it's rejected if it starts with a forbidden prefix. Defense in depth.

### Integration Point

The validator does NOT integrate into the live codebase in Wave 17 (because the Queen has no CONFIG_UPDATE tool). It ships as a tested, importable module ready for Wave 18 integration:

```python
# Future Wave 18 integration in queen_runtime.py or wherever CONFIG_UPDATE lands:
from formicos.surface.config_validator import validate_config_update

result = validate_config_update(directive_payload)
if not result.valid:
    log.warning("config_update_rejected", error=result.error)
    # Emit rejection chat message to operator
    return
# Apply validated update
```

---

## §4. Docker Compose Optimization (Track C, C1–C3)

### Reference: Operator's Proven anyloom Config

The operator runs 131k context on the same RTX 5090 with Qwen3-30B-A3B Q4_K_M. The anyloom compose proves the hardware can handle dramatically more than the current 8192 default. Key flags from that config that FormicOS should adopt:

### `--fit on` (Auto-size KV cache)

llama.cpp's `--fit` flag automatically sizes the KV cache to fit available VRAM. This is the single most important safety net for higher context sizes — it prevents OOM by dynamically adjusting rather than requiring manual VRAM budgeting. With `--fit on`, you can set an ambitious `--ctx-size` and the server will use as much as fits.

```yaml
--fit on
```

### `GGML_CUDA_GRAPH_OPT=1`

Enables CUDA graph optimization in the ggml backend. Captures and replays GPU kernel sequences, reducing launch overhead. Free performance on supported GPUs (Ampere and later, including Blackwell/RTX 5090).

```yaml
environment:
  - GGML_CUDA_GRAPH_OPT=1
```

### Larger Batch Sizes

The anyloom config uses `--batch-size 8192` and `--ubatch-size 4096` (2× the current FormicOS values). This doubles prompt processing throughput without affecting VRAM usage for the model weights.

```yaml
--batch-size 8192
--ubatch-size 4096
```

### `-sps 0.5` (Slot Prompt Similarity)

Controls how aggressively llama.cpp reuses cached prompt prefixes across slots. Default is 0.0 (disabled). At 0.5, slots with ≥50% prompt overlap share the cached prefix. For multi-agent workloads where agents share system prompts and colony context, this significantly reduces redundant processing.

```yaml
-sps ${LLM_SLOT_PROMPT_SIMILARITY:-0.5}
```

### `--reasoning-format none`

Suppresses the reasoning/think-token format that some models emit. For standard agent tasks (not chain-of-thought reasoning), this removes overhead tokens that inflate context and slow generation.

```yaml
--reasoning-format none
```

### `--cache-ram 1024`

Prompt caching in system RAM (not VRAM). Previously computed KV cache states are stored and reused when new requests share a prompt prefix. For multi-agent workloads with shared system prompts, this significantly reduces time-to-first-token. The prealpha used this; the live compose doesn't.

```yaml
--cache-ram ${LLM_CACHE_RAM:-1024}
```

### `ipc: host`

Shares the host's IPC namespace with the container. Required for CUDA IPC (inter-process communication) which reduces memory copy overhead between the CUDA runtime and the container.

```yaml
ipc: host
```

### Slot Parameterization

The current `-np 2` is hardcoded. Parameterize for operator tuning:

```yaml
-np ${LLM_SLOTS:-2}
```

The adapter's `_LOCAL_CONCURRENCY_LIMIT` in `llm_openai_compatible.py` must match the slot count, or requests queue/reject incorrectly. Document this coupling prominently in `.env.example`.

### Embed GPU Layers

```yaml
# In docker-compose.yml formicos-embed service:
--n-gpu-layers ${EMBED_GPU_LAYERS:-99}
```

Setting `EMBED_GPU_LAYERS=0` moves embedding to CPU, freeing ~700MB VRAM.

### Context Size Strategy

The current 8192 default is a relic of early conservative development. The operator's anyloom stack proves 131k works on the same hardware. With `--fit on` providing an OOM safety net, the risk of a higher default is low.

**Recommended approach:**
1. Add `--fit on` first (safety net)
2. Set default to `${LLM_CONTEXT_SIZE:-32768}` as a conservative 4× bump
3. Document in `.env.example` that 65536–131072 is proven stable on RTX 5090 with this model
4. Gate the final production default on real VRAM telemetry from A1 if the probe lands, or on a manual stability test with `--fit on` if it doesn't
5. When context goes up, bump `config/formicos.yaml` `context.total_budget_tokens` proportionally (4000 → 8000+) and the registry `context_window` for `llama-cpp/gpt-4`

### Complete Compose LLM Service (Target State)

```yaml
llm:
  image: ${LLM_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda}
  container_name: formicos-llm
  ports:
    - "${LLM_PORT:-8008}:8080"
  volumes:
    - ${LLM_MODEL_DIR:-./.models}:/models:ro
  environment:
    - GGML_CUDA_GRAPH_OPT=1
  command: >
    --model /models/${LLM_MODEL_FILE:-Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf}
    --alias gpt-4
    --ctx-size ${LLM_CONTEXT_SIZE:-32768}
    --n-gpu-layers 99
    --flash-attn on
    --fit on
    --cache-type-k q8_0
    --cache-type-v q8_0
    --batch-size 8192
    --ubatch-size 4096
    --threads 8
    --threads-batch 16
    --jinja
    --reasoning-format none
    --slots
    -np ${LLM_SLOTS:-2}
    -sps ${LLM_SLOT_PROMPT_SIMILARITY:-0.5}
    --cache-ram ${LLM_CACHE_RAM:-1024}
    --host 0.0.0.0
    --port 8080
  ipc: host
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  restart: unless-stopped
  healthcheck:
    test: ["CMD-SHELL", "curl -sf http://localhost:8080/health || exit 1"]
    interval: 10s
    timeout: 10s
    retries: 5
    start_period: 120s
```

---

## §5. Provider Health Visibility (Track A, A3)

### Current State

`view_state._build_cloud_endpoints()` derives status from API key presence only:
```python
status = "connected" if api_key_set else "no_key"
```

A provider can be cooled down (ADR-024) or rate-limited, but the snapshot still shows "connected."

### Fix

Expose cooldown state from `LLMRouter` in `runtime.py`. The router already tracks provider health internally. Add a method:

```python
# In LLMRouter:
def provider_health(self) -> dict[str, str]:
    """Return current health status per provider prefix."""
    result = {}
    for provider in self._adapters:
        if self._is_cooled_down(provider):
            result[provider] = "cooldown"
        else:
            result[provider] = "ok"
    return result
```

Then in `view_state._build_cloud_endpoints()`:

```python
# If runtime is available, check cooldown state:
router_health = router.provider_health() if router else {}
for provider in cloud_providers:
    if not api_key_set:
        status = "no_key"
    elif router_health.get(provider) == "cooldown":
        status = "cooldown"
    else:
        status = "connected"
```

Frontend `CloudEndpoint` type already has a `status` field that accepts strings — add `'cooldown'` to the union.

---

## §6. Smoke Trace Protocol

Each trace follows the pattern: trigger → observe at each pipeline stage → verify at the terminal display.

### Trace 1: Slot Utilization

```
1. Start stack with docker compose up
2. Wait for LLM healthcheck green
3. Connect WebSocket client
4. Receive state snapshot
5. VERIFY: snapshot.localModels[0].slotsTotal == 2
6. VERIFY: snapshot.localModels[0].slotsIdle + slotsProcessing == slotsTotal
7. Spawn a colony (triggers LLM inference)
8. During inference, reconnect WS
9. VERIFY: snapshot.localModels[0].slotsProcessing >= 1
```

### Trace 2: Routing Decision

```
1. Start stack, spawn colony with heavy-tier agent
2. VERIFY: structlog output contains "compute_router.route" with reason
3. VERIFY: telemetry.jsonl contains "routing_decision" event
4. VERIFY: event payload contains caste, phase, selected_model, reason
```

### Trace 3: Model Policy Edit

```
1. Open model registry in UI
2. Expand a model card, edit maxOutputTokens
3. Save
4. VERIFY: formicos.yaml updated with new value
5. Restart server
6. VERIFY: model registry shows persisted value
```

### Trace 4: Provider Health

```
1. Case A: leave ANTHROPIC_API_KEY empty
2. Start stack
3. VERIFY: snapshot.cloudEndpoints shows status "no_key" for anthropic
4. Case B: set ANTHROPIC_API_KEY to a non-empty invalid value and restart
5. VERIFY: snapshot does NOT lie with "no_key" for a present key
6. Spawn colony that routes to anthropic
7. VERIFY: fallback triggers, colony chat shows the failure/fallback path
8. VERIFY: next snapshot degrades honestly (for example "cooldown" if A3 landed)
```
