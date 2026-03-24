# Pre-Alpha → Alpha: Definitive Insights for Wave 17+

**Date:** 2026-03-15
**Alpha state:** Wave 16 complete. 1069 tests, 35→36 events, ~6,500 Python LOC, ~3,400 frontend LOC.
**Pre-alpha state:** v0.12.20 "Close the Loops". 66K Python LOC, 6866 tests, 55 coder terminals, 19 phases.

---

## The headline

The alpha is a better architecture in 10% of the code. The pre-alpha proved what works through 20 development phases and 100+ colony runs but collapsed under its own weight — 66K LOC, monolithic files (agents.py: 91K, orchestrator.py: 77K, colony_manager.py: 137K), and cross-module coupling that required 55 coder terminals just to close broken data paths in the final release.

Six patterns from the prototype survived that gauntlet and are directly applicable to the alpha without violating its 15K LOC budget or hexagonal layer discipline. Three more are research-grade ideas worth tracking but not porting yet.

---

## Tier 1: Port now (wave 17, ~6 hours total)

### 1. CONFIG_UPDATE Validator (294 LOC → ~150 LOC adapted)

**Why it matters:** The alpha's Queen emits CONFIG_UPDATE directives via `queen_runtime.py`. If the LLM hallucinates a bad payload, the colony manager applies it unvalidated. The prototype crashed from this repeatedly until v0.12.3 added `config_validator.py`.

**What to port:**
- Forbidden string scan: `rm -rf`, `eval(`, `__import__`, `<script>`, `subprocess.`, shell expansions, null bytes
- Recursive depth guard (max 4 levels)
- NaN/Inf rejection
- Param path whitelist (only known paths accepted)
- Type + range enforcement per path
- Payload length cap (2048 chars)

**Where it goes in the alpha:** `src/formicos/surface/config_validator.py`. Pure validation — no imports from engine/adapters. Called by `colony_manager.py` before applying any CONFIG_UPDATE to the context tree.

**The prototype also has `FORBIDDEN_CONFIG_PATHS`** in `research/quality_gate.py` — a deny-list of security-critical paths the Queen can never mutate (auth, API keys, ports, database, MCP server definitions, workspace roots). This is the second defense layer: even if a param_path passes the whitelist, it's rejected if it touches infrastructure.

**Alpha file:** `config_validator.py` is already in the wave 17 lessons folder. Adapt the `PARAM_RULES` dict to match the alpha's actual `caste_recipes.yaml` paths.

### 2. Experimentable Parameters Whitelist (YAML config)

**Why it matters:** The alpha needs to know which parameters the Queen can experiment with. Without a whitelist, the experiment engine (when added) has no bounds.

**What to port:** `config/experimentable_params.yaml` — defines per-caste temperature ranges, max_tokens bounds, and governance trigger thresholds. Already in the wave 17 lessons folder.

**Where it goes:** `config/experimentable_params.yaml`. The config validator references it.

### 3. Sandbox Profiles (YAML config)

**Why it matters:** Wave 14 added `CodeExecuted` events and ADR-023 defined per-caste tool permissions, but the alpha has no sandbox profile definitions. The prototype's `config/sandbox_profiles.yaml` defines the actual runtime parameters.

**What to port:** Three profiles relevant to the alpha:
- `harness`: Dev/test, no Docker, fast execution
- `local_sandboxed`: gVisor + Docker, no network, 512MB memory, 128 PIDs
- `queen_sandbox`: Elevated privileges, network allowed, 2048MB memory

**Where it goes:** `config/sandbox_profiles.yaml`. The alpha's sandbox port (defined but unadapted per PROGRESS.md) consumes these.

### 4. Instrumentation Bus (180 LOC → ~120 LOC adapted)

**Why it matters:** The alpha has event sourcing for domain events (ColonySpawned, RoundCompleted, etc.) but no separate telemetry channel for operational metrics. The prototype learned the hard way that mixing telemetry with domain events bloats the event store and slows replay. v0.12.10 introduced the `InstrumentationBus` specifically to solve this.

**What to port:**
- Bounded async queue (10K capacity, overflow drops oldest, never blocks)
- Pre-start buffering (events emitted before the async loop starts are queued in a thread-safe deque, migrated on `start()`)
- Fan-out to registered sinks with failure isolation
- Typed emit functions: `emit_routing_decision()`, `emit_token_expenditure()`, `emit_tool_call()`, `emit_skill_retrieval()`

**Where it goes:** `src/formicos/engine/telemetry_bus.py` (imports only core types). Sinks go in adapters (JSONL file sink, Context Tree sink for dashboard metrics).

**The prototype's v0.12.20 release packet explicitly calls out "TelemetryStoreSink bridges InstrumentationBus events to TelemetryStore (SQLite). 7 event types routed."** This was a top deliverable of the final release — it's the pattern that made observability work.

### 5. Queen Hypothesis Engine (200 LOC → ~120 LOC adapted)

**Why it matters:** The alpha's Queen can emit EXPERIMENT directives, but has no structured way to track what happened. The prototype's hypothesis engine tracks each hypothesis through `PROPOSED → EXPERIMENT_EMITTED → CONFIRMED | REFUTED | EXPIRED` with rolling storage (200 entries max, 3K chars context budget).

**What to port:**
- `HypothesisStatus` enum (5 states)
- `QueenHypothesis` model (links knowledge gap → experiment group → outcome)
- `format_hypothesis_context()` — builds a prompt block for the Queen showing active hypotheses and past outcomes
- Rolling-cap storage in the context tree's supercolony scope

**Where it goes:** `src/formicos/surface/hypothesis_tracker.py` (surface layer, since it reads/writes context tree state). The model types go in core/types.py.

### 6. Knowledge Gap Analyzer (266 LOC → ~150 LOC adapted)

**Why it matters:** The alpha extracts skills from completed colonies but has no mechanism to identify what the skill bank is *missing*. The prototype's `GapAnalyzer` scans knowledge gaps and proposes RESEARCH directives with automatic source selection via keyword matching.

**What to port:**
- Gap ranking by priority and specificity
- Keyword → source mapping (arxiv, github, huggingface)
- Automatic RESEARCH directive payload construction
- Quality gate with configurable relevance threshold (0.7 default)
- `FORBIDDEN_CONFIG_PATHS` deny-list for security-critical paths

**Where it goes:** `src/formicos/surface/gap_analyzer.py`. Reads from context tree, produces directive payloads. The quality gate is a pure function that can live in core/.

---

## Tier 2: Track for wave 18+ (valuable but premature)

### 7. Routing Learner (530 LOC)

The prototype's `routing_learner.py` uses EMA-based quality tracking to adjust compute router policy based on historical experiment outcomes. The alpha's compute router (wave 9) is config-driven with static caste×phase rules. The learner adds adaptive refinement. Worth adding once the experiment engine is running and producing outcome data.

### 8. RAG Gating (reliability/models.py)

Three-tier confidence gating for RAG results: high confidence (trusted), advisory (injected with caveat), discarded (below threshold). The alpha's skill lifecycle (wave 9) has composite scoring but no explicit gating with caveat labels. This matters when the skill bank grows past ~500 entries and low-relevance results start polluting context.

### 9. Colony Summary Model (reliability/models.py)

Structured colony outcome summaries for cross-colony learning. The alpha has `ColonyCompleted` events with `quality_score` and `skills_extracted`, but no structured summary model that captures what the colony learned, what failed, and what to try differently. This feeds the hypothesis engine.

---

## Tier 3: Do NOT port (prototype sprawl the alpha correctly avoided)

| Module | LOC | Why skip |
|---|---|---|
| Diplomat/WAN federation | 1,020 | Premature. No multi-node deployment. |
| CFO metering + Stripe | 431 | Prototype-specific billing. Alpha tracks cost internally. |
| Skill bank sync (cross-node) | 267 | Federation-specific. Single-node alpha. |
| EvoFlow NSGA-II | 640 | Genetic algorithm for experiments. Premature without experiment engine. |
| SPO evaluator (LLM-as-judge) | 320 | Useful but not until experiments run. |
| Dashboard package | 4,445 | Alpha has its own Lit Web Components UI. |
| Supercolony digest | 596 | Cross-colony Queen context. Defer to multi-colony wave. |
| Chat threading | 490 | Alpha has ColonyChatMessage events. Different approach. |

---

## Cross-cutting lesson from the prototype's death

The v0.12.20 release packet reveals the root cause of the prototype's failure: **broken data paths**. The release codename was literally "Close the Loops" — 19 phases and 55 coder terminals spent closing wired-but-incomplete data flows where metrics endpoints returned empty, governance detectors received no input, and config mutations weren't versioned.

The alpha avoids this by design: event sourcing means every state change is an event, projections rebuild from events, and the projection store is the single source of truth for the UI. But the alpha should add one practice from the prototype's painful lesson: **a data flow smoke test per wave that verifies every new metric/config/governance path actually delivers data end-to-end, not just that the endpoint exists.**

The prototype's v0.12.20 validation ledger ran 19 manual smoke checks tracing data from source to dashboard. The alpha's smoke protocol (wave 15) covers colony lifecycle but not telemetry/config paths. Adding 3-5 data flow traces per wave catches "wired but empty" bugs before they accumulate.

---

## What the alpha does that the prototype never figured out

For completeness — the alpha's structural advantages that should never regress:

1. **15K LOC budget** — the prototype had no budget and grew to 66K
2. **4-layer hexagonal architecture** with lint-enforced import rules — the prototype had no layer discipline
3. **Event sourcing with typed frozen events** — the prototype used mutable Context Tree writes
4. **msgspec-speed events** — the prototype used Pydantic everywhere
5. **Single mutation path** (`Runtime.emit_and_broadcast`) — the prototype had dozens of mutation points
6. **Projection replay** — the prototype needed 55 terminals to "close the loops" because state was scattered
7. **Clean config cascade** (formicos.yaml → workspace override → template) — the prototype had config spaghetti across 15 YAML files
