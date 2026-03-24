# Prototype Mining Report: What the Old Codebase Has That the Alpha Should Take

**Date:** 2026-03-15
**Source:** `/home/claude/scratchpad/Formic-OS/` (prototype, v0.9.0 → v0.12.20, ~66K LOC)
**Target:** Alpha codebase (wave 15/16 complete)
**Method:** Compared prototype modules against wave 15/16 algorithms.md to identify concrete patterns worth porting

---

## Executive Summary

The prototype grew to 66K LOC across 60+ modules — far beyond the alpha's 15K LOC budget. Most of it is sprawl that the alpha correctly avoided. But **six concrete patterns** are production-hardened and directly portable to the alpha without architectural changes. Three are config files that can be dropped in unchanged. Three are code patterns that need adaptation to the alpha's event-sourced hexagonal architecture.

---

## 1. CONFIG_UPDATE Validator — Port Directly (highest priority)

**Prototype file:** `src/config_validator.py` (294 lines)
**Alpha gap:** The alpha has Queen-driven CONFIG_UPDATE directives but no validation guardrails against hallucinated payloads.

The prototype's validator is a self-contained, battle-hardened module that prevents the colony manager from crashing when the Queen LLM outputs bad config updates. It includes:

- **Forbidden string scanning:** Catches `rm -rf`, `eval(`, `__import__`, `<script>`, `subprocess.`, shell expansions (`$((`, `${`), and null bytes. Recursive scan through nested dicts/lists.
- **Recursive depth guard:** Rejects payloads nested deeper than 4 levels (prevents stack overflow from adversarial JSON).
- **NaN/Inf guard:** Rejects `float("nan")`, `float("inf")`, and string representations like `"NaN"`, `"infinity"`.
- **Param path whitelist:** Only known `param_path` values are accepted (e.g., `recipes.coder.temperature`). Unknown paths are rejected, not silently ignored.
- **Type + range enforcement:** Temperature must be float 0.0–2.0, max_tokens must be int 500–8000, etc. Rules are declared as a static dict.
- **Payload length guard:** Rejects raw JSON strings > 2048 chars.
- **Batch validation API:** `validate_config_update_batch()` returns `(valid, rejected)` tuples for processing multiple directives.

**Port strategy:** Copy `config_validator.py` into the alpha's surface layer (it has no internal imports except Pydantic). Update `PARAM_RULES` to match the alpha's actual caste recipe paths. Wire `validate_config_update()` into the colony manager's CONFIG_UPDATE handler — call it before applying the update to the Context Tree.

**Estimated effort:** 30 minutes. The module is self-contained.

---

## 2. Experimentable Parameters Whitelist — Drop In Unchanged

**Prototype file:** `config/experimentable_params.yaml`
**Alpha gap:** The alpha's experiment engine needs a parameter whitelist but wave 15/16 doesn't define one.

This YAML defines exactly which caste recipe parameters the Queen can experiment with, with type and range bounds:

- Coder temperature: float 0.0–1.0
- Coder max_tokens: int 1000–16000
- Coder context_window: int 4096–131072
- Architect/Researcher/Manager/Reviewer temperatures with per-caste ranges
- Governance triggers: stall_repeat_threshold (int 2–10), similarity_threshold (float 0.70–0.99), rounds_before_force_halt (int 1–10)

**Port strategy:** Copy to `config/experimentable_params.yaml`. The config validator (item 1) already references it.

---

## 3. Routing Table YAML — Adapt for Alpha's Tier System

**Prototype file:** `config/routing_table.yaml`
**Alpha gap:** Wave 15/16 has caste tier assignments (heavy/standard/light) in templates but no YAML-driven routing table for the compute router.

The prototype's routing table maps roles to default + fallback models with optional VRAM throttle thresholds. The alpha should adapt this to work with its tier system:

```yaml
# Alpha adaptation — tier-based routing with fallback
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

The prototype also has `config/compute_routing.yaml` with per-caste/per-phase rules and a `learner` section with EMA hyperparameters. The learner config (`ema_alpha: 0.3`, `complexity_cloud_threshold: 0.75`, etc.) represents tuned values from prototype experiments.

**Port strategy:** Create `config/routing_table.yaml` adapting the prototype format to use tiers instead of roles. Carry over the VRAM throttle concept and the learner hyperparameters.

---

## 4. Instrumentation Bus — Pattern Worth Adopting

**Prototype file:** `src/instrumentation/bus.py` (~180 lines)
**Alpha gap:** The alpha has event sourcing for domain events but no lightweight telemetry bus for operational metrics (token expenditure, routing decisions, tool calls, skill retrieval hits/misses).

The prototype's `InstrumentationBus` is a clean, bounded-queue async event bus with:

- **Bounded FIFO with overflow drop:** 10K event capacity. On overflow, drops oldest event (never blocks). This is critical for production — a blocked telemetry path kills the colony.
- **Pre-start buffering:** Events emitted before the async loop starts are queued in a thread-safe deque, then migrated to an `asyncio.Queue` on `start()`. This handles the startup race condition where hooks fire before the bus is running.
- **Fan-out to sinks:** Registered async callables receive every event. Sink failures are caught and logged, never propagated.
- **Singleton pattern:** `get_bus()` returns a module-level singleton. `reset_bus()` for tests.
- **Non-blocking emit:** `emit_nowait()` is synchronous (safe to call from any context), `emit()` is async (delegates to `emit_nowait`).

The hooks module (`src/instrumentation/hooks.py`) provides typed emit functions: `emit_routing_decision()`, `emit_token_expenditure()`, `emit_tool_call()`, `emit_skill_retrieval()`, `emit_governance_event()`, `emit_fleet_event()`, `emit_challenge_event()`. Each constructs an `InstrumentationEvent` with typed payload and calls `get_bus().emit_nowait()`.

**Port strategy:** The alpha's event store handles domain events (ColonySpawned, RoundCompleted, etc.). The instrumentation bus handles operational telemetry that shouldn't pollute the domain event stream. Create `src/formicos/engine/telemetry_bus.py` with the same bounded-queue pattern. Register a JSONL sink for debugging and a Context Tree sink for dashboard metrics. The bus lives in engine/ (imports only core types).

**Estimated effort:** 2 hours. The pattern is clean but needs adaptation to the alpha's layer model.

---

## 5. Sandbox Profile Escalation — Config Worth Porting

**Prototype file:** `config/sandbox_profiles.yaml`
**Alpha gap:** Wave 15/16 references sandbox profiles but doesn't include the actual profile definitions.

The prototype defines a tiered sandbox hierarchy:

| Profile | Runtime | Isolation | Network | Memory | PIDs | Use Case |
|---|---|---|---|---|---|---|
| harness | (none) | local_harness | No | 512MB | 128 | Dev/test, fast execution |
| local_trusted | runc | cgroups | Yes | 2048MB | 512 | Trusted local ops |
| local_sandboxed | runsc | gVisor | No | 512MB | 128 | Default worker isolation |
| queen_sandbox | (none) | local_harness | Yes | 2048MB | 512 | Queen with network access |
| peer_strict | runsc | gVisor | No | 256MB | 64 | Cross-node spillover |
| wan_maximum | runsc | gVisor | No | 128MB | 48 | Future WAN (not enabled) |

The `ProfileEscalator` in `src/sandbox/escalation.py` auto-escalates profiles based on trust level and failure history.

**Port strategy:** Copy `config/sandbox_profiles.yaml` and prune to the 3 profiles the alpha actually needs: `harness` (dev), `local_sandboxed` (production default), `queen_sandbox` (Queen). Drop the WAN profiles for now.

---

## 6. Queen Hypothesis Engine — Extract the State Machine

**Prototype file:** `src/queen/hypothesis_engine.py` (~200 lines)
**Alpha gap:** The alpha's Queen can emit EXPERIMENT directives but has no structured hypothesis lifecycle tracking.

The prototype tracks each hypothesis through a state machine:

```
PROPOSED → EXPERIMENT_EMITTED → CONFIRMED | REFUTED | EXPIRED
```

Each `QueenHypothesis` links a knowledge gap to an experiment group with:
- `hypothesis_id`: Unique identifier
- `knowledge_gap`: The gap from the Context Tree that motivated this
- `experiment_group`: Name from `config/evoflow.yaml`
- `reasoning`: Queen's 1-2 sentence justification
- `proposed_changes`: List of `{param_path, variant_value}` dicts
- `status`: The lifecycle state
- `emitted_directive_id`: Links to the EXPERIMENT directive

The hypothesis log is stored in the Context Tree's supercolony scope with a rolling cap of 200 entries and a context-window budget of 3000 chars. The `format_hypothesis_context()` function builds a prompt block showing active hypotheses and past outcomes for the Queen's decision-making.

**Port strategy:** The hypothesis model and state machine are directly portable. Create `QueenHypothesis` as a frozen dataclass in core/. The lifecycle functions (format context, log, resolve) go in engine/. The rolling-cap storage pattern integrates with the alpha's Context Tree. This is foundational for the self-evolution flywheel — without hypothesis tracking, the Queen can't learn from experiment outcomes.

**Estimated effort:** 3 hours. Needs adaptation to alpha's event-sourced persistence (hypotheses should be events, not raw Context Tree writes).

---

## What NOT to port

The prototype has 66K LOC for a reason — most of it is sprawl that violates the alpha's architectural principles:

- **Diplomat/WAN federation** (1020 LOC) — premature for alpha. Punt to post-alpha.
- **CFO metering with Stripe** (431 LOC) — prototype-specific billing. Alpha uses simpler cost tracking.
- **Skill bank sync** (267 LOC) — federation-specific. Alpha doesn't need cross-node skill sync yet.
- **SPO evaluator** (320 LOC) — LLM-as-judge for experiments. Useful but not until the experiment engine is running.
- **EvoFlow NSGA-II** (640 LOC) — multi-objective genetic algorithm for experiment optimization. Fascinating but premature — the alpha needs the basic experiment engine working first.
- **Dashboard package** (4445 LOC) — the alpha has its own Lit Web Components UI. Prototype's dashboard is incompatible.
- **Supercolony digest** (596 LOC) — cross-colony Queen context builder. Useful later, not now.
- **Reliability models** (1093 LOC) — RAG gating, directive rejection, flip-flop config, sycophancy checking. Valuable eventually but adds complexity before the basics work.

---

## Priority ordering for wave 17+

1. **Config validator** (30 min) — prevents Queen hallucination crashes. Immediate safety win.
2. **Experimentable params YAML** (5 min) — drop-in config file.
3. **Sandbox profiles YAML** (10 min) — drop-in config file with pruning.
4. **Routing table YAML** (30 min) — adapt to tier system.
5. **Instrumentation bus** (2 hours) — enables operational telemetry without polluting domain events.
6. **Hypothesis engine** (3 hours) — foundational for self-evolution flywheel.

Total: ~6 hours of porting work for the six highest-value patterns.
