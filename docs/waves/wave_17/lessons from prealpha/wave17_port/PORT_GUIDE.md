# Wave 17 Port Guide: Pre-Alpha → Alpha Implementation Steps

**Contents of this package:**

```
wave17_port/
├── PORT_GUIDE.md          ← this file
├── config/
│   ├── experimentable_params.yaml   ← drop-in (item 2)
│   ├── sandbox_profiles.yaml        ← prune and drop-in (item 3)
│   └── routing_table.yaml           ← adapt to tier system (item 4)
├── surface/
│   └── config_validator.py          ← adapted for alpha (item 1)
└── engine/
    └── telemetry_bus.py             ← adapted for alpha (item 5)
```

Items 6 (hypothesis engine) and 7 (gap analyzer) are documented below
with implementation specs but NOT shipped as files — they need tighter
integration with the alpha's existing queen_runtime.py and skill_lifecycle.py.

---

## Item 1: Config Validator (PRIORITY: CRITICAL)

**File:** `surface/config_validator.py` (already adapted)
**Effort:** 30 minutes integration
**Dependencies:** None — pure validation, no engine/adapter imports

### Integration steps

1. Copy `surface/config_validator.py` to `src/formicos/surface/config_validator.py`

2. In `src/formicos/surface/colony_manager.py`, find where CONFIG_UPDATE
   directives are applied. Before the context tree write, add:

   ```python
   from formicos.surface.config_validator import validate_config_update

   result = validate_config_update(directive.payload)
   if not result.valid:
       log.warning("config_update_rejected", error=result.error,
                   param_path=result.param_path)
       # Emit a chat message so the operator sees the rejection
       await self._emit_chat(colony_id, f"⚠ Config update rejected: {result.error}")
       return
   ```

3. Update PARAM_RULES paths if any caste_recipes.yaml paths differ from
   what's in the file. The current paths assume `castes.{name}.{field}` —
   verify against the live config structure.

4. Add tests:
   - Valid payload passes
   - Unknown param_path rejected
   - Out-of-range value rejected
   - Forbidden string detected
   - NaN/Inf rejected
   - Forbidden config prefix rejected
   - Oversized payload rejected

### What the prototype learned

The v0.12.3 audit doc describes this bug: "Queen LLM hallucinates a bad
CONFIG_UPDATE directive" causing colony_manager crashes. This happened
repeatedly in endurance runs (100+ colonies). The validator was the fix.

---

## Item 2: Experimentable Params (PRIORITY: HIGH)

**File:** `config/experimentable_params.yaml` (drop-in)
**Effort:** 5 minutes

### Integration steps

1. Copy to `config/experimentable_params.yaml`
2. The config validator already references these paths
3. When the experiment engine is added, it loads this YAML as the mutation
   whitelist — params not listed here cannot be experimented with

---

## Item 3: Sandbox Profiles (PRIORITY: MEDIUM)

**File:** `config/sandbox_profiles.yaml` (prune and drop-in)
**Effort:** 10 minutes

### Integration steps

1. Copy to `config/sandbox_profiles.yaml`
2. Prune to 3 profiles the alpha needs now:
   - `harness` → dev/test (no Docker)
   - `local_sandboxed` → production default (gVisor)
   - `queen_sandbox` → Queen elevated privileges
3. Remove `peer_strict`, `wan_maximum`, `local_trusted`, `sandboxed`
   (duplicates or federation-only)
4. The alpha's sandbox port (defined in core/ports.py but unadapted per
   PROGRESS.md known limitations) consumes these when implemented

---

## Item 4: Routing Table (PRIORITY: MEDIUM)

**File:** `config/routing_table.yaml` (adapt to tier system)
**Effort:** 30 minutes

### Integration steps

1. Copy to `config/routing_table.yaml`
2. The prototype routes by role (coder, reviewer, etc.). The alpha routes
   by tier (heavy, standard, light). Adapt:

   ```yaml
   default_model: "local/qwen3-30b"
   default_fallback: "cloud/claude-haiku-4-5"
   routes:
     - tier: "heavy"
       default_model: "cloud/claude-sonnet-4-5"
       fallback_model: "cloud/claude-haiku-4-5"
     - tier: "standard"
       default_model: "local/qwen3-30b"
       fallback_model: "cloud/claude-haiku-4-5"
       throttle_threshold_vram_mb: 20000
     - tier: "light"
       default_model: "local/qwen3-30b"
       fallback_model: "local/qwen3-30b"
   ```

3. The alpha's compute router in `engine/runner.py` (wave 9) reads from
   `formicos.yaml`. Either extend that config section or load this as a
   separate file — the prototype used a separate file for cleaner editing.

---

## Item 5: Telemetry Bus (PRIORITY: HIGH)

**File:** `engine/telemetry_bus.py` (already adapted)
**Effort:** 2 hours integration

### Integration steps

1. Copy `engine/telemetry_bus.py` to `src/formicos/engine/telemetry_bus.py`

2. In `src/formicos/surface/app.py` lifespan, start/stop the bus:

   ```python
   from formicos.engine.telemetry_bus import get_telemetry_bus

   async with lifespan():
       bus = get_telemetry_bus()
       await bus.start()
       # ... existing lifespan code ...
       yield
       await bus.stop()
   ```

3. Add a JSONL sink for debugging (adapters layer):

   ```python
   # src/formicos/adapters/telemetry_jsonl.py
   import json
   from pathlib import Path
   from formicos.engine.telemetry_bus import TelemetryEvent

   class JSONLSink:
       def __init__(self, path: Path):
           self._path = path
       async def __call__(self, event: TelemetryEvent) -> None:
           line = event.model_dump_json() + "\n"
           self._path.open("a").write(line)
   ```

4. Wire emit helpers into existing code:
   - `emit_routing_decision()` in runner.py where compute routing happens
   - `emit_token_expenditure()` in runner.py after each LLM call
   - `emit_tool_call()` in runner.py tool execution loop
   - `emit_skill_retrieval()` in context.py skill retrieval path

5. Add tests:
   - Event queued before start() is delivered after start()
   - Overflow drops oldest, not newest
   - Sink failure doesn't crash the bus
   - stop() drains remaining events

---

## Item 6: Hypothesis Engine (PRIORITY: MEDIUM — wave 17 or 18)

**NOT shipped as a file** — needs design decisions about alpha integration.

### What to port from the prototype

The prototype's `src/queen/hypothesis_engine.py` (200 LOC) tracks:

```
PROPOSED → EXPERIMENT_EMITTED → CONFIRMED | REFUTED | EXPIRED
```

Each QueenHypothesis links:
- knowledge_gap → experiment_group → proposed_changes → outcome

### Where it goes in the alpha

- `HypothesisStatus` enum → `src/formicos/core/types.py`
- `QueenHypothesis` model → `src/formicos/core/types.py`
- Lifecycle functions → `src/formicos/surface/queen_runtime.py` (extend)
- Storage: Context Tree supercolony scope, rolling cap of 200 entries

### Alpha-specific adaptation

The alpha should emit hypothesis events (not raw Context Tree writes):
- `HypothesisProposed` event
- `HypothesisResolved` event (with status: confirmed/refuted/expired)

These feed the projection store and become visible in the Queen overview.

### Key detail from prototype

The `format_hypothesis_context()` function builds a prompt block with a
3000-char budget. The Queen reads this to decide which experiment to run
next. Without this, the Queen has no memory of what experiments already
ran and what they found — leading to repeated experiments.

---

## Item 7: Gap Analyzer (PRIORITY: MEDIUM — wave 18+)

**NOT shipped as a file** — needs the experiment engine first.

### What to port from the prototype

The prototype's `src/research/gap_analyzer.py` (266 LOC) does:

1. Parses knowledge gaps from Context Tree
2. Ranks by priority and specificity
3. Maps keywords to research sources (arxiv, github, huggingface)
4. Constructs RESEARCH directive payloads automatically

### Where it goes in the alpha

- `GapAnalyzer` class → `src/formicos/surface/gap_analyzer.py`
- Config: `config/research_sources.yaml` (defines valid source IDs)
- Called by: `queen_runtime.py` during Queen activation

### Prerequisite

The alpha needs the experiment engine and RESEARCH directive type before
this is useful. The gap analyzer produces directive payloads that the
experiment engine executes. Without execution, the analyzer's output
goes nowhere.

### Key detail from prototype

The `FORBIDDEN_CONFIG_PATHS` deny-list (ported into config_validator.py
above) was originally discovered through the gap analyzer path — the
Queen tried to "research" ways to improve performance by modifying
server ports and database config. The deny-list is the fix.

---

## Data Flow Smoke Test (add to every wave)

The prototype's final release (v0.12.20, 19 phases) was entirely dedicated
to closing broken data paths. The lesson: **every new metric/config/governance
path must be smoke-tested end-to-end, not just for endpoint existence.**

Add 3-5 traces per wave:

```
# Example trace: routing decision → telemetry bus → JSONL sink → dashboard
1. Spawn colony with heavy-tier agent
2. Verify: structured log shows "routing_decision" event
3. Verify: telemetry.jsonl contains the event
4. Verify: colony detail shows routed model badge

# Example trace: CONFIG_UPDATE → validator → context tree → snapshot
1. Trigger Queen CONFIG_UPDATE (via direct WS command in test)
2. Verify: valid update applied to context tree
3. Verify: invalid update rejected with error in colony chat
4. Verify: snapshot reflects the valid update
```

This catches "wired but empty" bugs before they accumulate into a
19-phase "Close the Loops" emergency release.
