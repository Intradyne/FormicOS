# ADR-039: Knowledge Metabolism -- Confidence Evolution, Thompson Sampling, Workflow Steps, and Legacy Deletion

**Status:** Proposed
**Date:** 2026-03-17
**Depends on:** ADR-017 (Bayesian confidence + LLM dedup), ADR-015 (event union discipline), ADR-010 (skill crystallization)

---

## Context

The institutional memory system (Waves 26-29) stores extracted skills and experiences but has no mechanism for confidence to evolve based on real colony outcomes. Entries start at confidence 0.5 and never change. Retrieval ranking is deterministic -- the same entries always win for a given query.

The legacy skill system (ADR-017) proved that Bayesian confidence tracking works: Beta distribution (alpha/beta), UCB exploration bonus, and LLM-gated deduplication. But that system was disabled at the write path in Wave 28 and its source files (`skill_lifecycle.py`, `skill_dedup.py`) have been dead code since.

Wave 29 added thread-scoped workflows and deterministic service handlers, creating the organizational structure for knowledge. What's missing is the feedback loop that makes knowledge compound: entries used by successful colonies should gain confidence, entries used by failed colonies should lose it, and retrieval should explore uncertain entries rather than always exploiting known-good ones.

Additionally, threads gained goal and completion semantics in Wave 29 but have no concept of typed workflow steps -- the Queen improvises each colony spawn without a visible plan.

---

## Decision

### 1. Port Beta distribution confidence to institutional memory

`MemoryEntry` gains `conf_alpha` and `conf_beta` fields (default 5.0 each, matching legacy `DEFAULT_PRIOR_STRENGTH = 10.0` split evenly). After colony completion, `_post_colony_hooks()` correlates `KnowledgeAccessRecorded` traces with colony outcome and emits `MemoryConfidenceUpdated` events:
- Colony succeeded: alpha += 1.0
- Colony failed: beta += 1.0

This is the same Bayesian update that ADR-017 specified for the legacy skill system, now applied to event-sourced institutional memory with durable confidence events.

### 2. Replace UCB with Thompson Sampling for retrieval

ADR-017's UCB exploration bonus (`ucb_exploration_weight * sqrt(ln(N) / n)`) is not ported. Instead, retrieval uses Thompson Sampling: sample from `Beta(alpha, beta)` per entry and rank by the sampled value.

Thompson Sampling is superior to UCB for this use case because:
- It naturally balances exploitation (high-confidence entries produce high samples) with exploration (uncertain entries produce high-variance samples)
- It does not require a global colony count parameter
- It is the standard approach in multi-armed bandit literature for balancing explore/exploit with Beta-distributed arms
- No production agent memory system implements this (per 2025-2026 landscape survey) -- this is novel

The composite scoring formula replaces the current `score + status_bonus + confidence * 0.1` in both `knowledge_catalog.py` and `memory_store.py` with: `0.35 * semantic + 0.25 * thompson_sample + 0.15 * freshness + 0.15 * status + 0.10 * thread_bonus`. Sign conventions differ between files (negative for ascending sort in catalog, positive for reverse=True in memory store) and are preserved.

### 3. Add workflow steps as thread metadata

New `WorkflowStep` model with description, expected outputs, status, and optional template reference. Two new events: `WorkflowStepDefined` (Queen declares steps) and `WorkflowStepCompleted` (emitted from `_post_colony_hooks` when a colony matching a running step completes -- never from a projection handler). `ColonySpawned` gains an additive `step_index` field for colony-to-step binding.

Steps are Queen scaffolding, not a pipeline engine. The Queen reasons about step status when deciding what to spawn next. Automatic step execution is deferred.

### 4. Thread archival with confidence decay

Thread lifecycle: active -> completed (goal satisfied, confidence retained) -> archived (no longer active, unpromoted knowledge decays). New `archive_thread` Queen tool emits `ThreadStatusChanged(new_status="archived")` then emits `MemoryConfidenceUpdated(reason="archival_decay")` for each unpromoted thread-scoped entry with decay formula `alpha *= 0.8, beta *= 1.2`. Produces N events for N entries per hard constraint #7 (every state change is an event).

### 5. Delete legacy skill system files

- `src/formicos/surface/skill_lifecycle.py` -- DELETE (confidence math ported, code dead since Wave 28)
- `src/formicos/adapters/skill_dedup.py` -- DELETE (dedup pattern ported to `maintenance.py`, code dead since Wave 28)
- `frontend/src/components/skill-browser.ts` -- DELETE (imports removed in Wave 28)
- `_crystallize_skills()` method body in `colony_manager.py` -- DELETE (call site disabled since Wave 28)

### 6. Open event union from 45 to 48

Three new events:
- `MemoryConfidenceUpdated` -- entry confidence changed (colony outcome or archival decay)
- `WorkflowStepDefined` -- step declared on a thread
- `WorkflowStepCompleted` -- step's colony completed

Per ADR-015, all three have emitters (colony_manager, queen_runtime) and projection handlers at the time they enter the union.

---

## Explicitly NOT Decided

- **Automatic step execution.** Steps are Queen-guided. Auto-spawning the next step when a predecessor completes is Wave 31.
- **Cross-workspace knowledge sharing.** Knowledge scopes to workspace + thread. Cross-workspace is a different scope.
- **Confidence-weighted extraction.** Whether to extract more aggressively from high-confidence colonies is speculative.
- **Agent-directed knowledge exploration.** RLM-style progressive disclosure deepening is Wave 31.

---

## Consequences

### Modified files

**Core (contract changes):**
- `core/types.py`: conf_alpha/conf_beta on MemoryEntry, WorkflowStep/WorkflowStepStatus
- `core/events.py`: 3 new events, step_index on ColonySpawned, union 45->48
- `core/ports.py`: 3 new event names

**Surface:**
- `colony_manager.py`: confidence update + step completion in _post_colony_hooks
- `projections.py`: 3 new handlers, step "running" derivation, workflow_steps field
- `knowledge_catalog.py`: Thompson Sampling _composite_key, _compute_freshness
- `memory_store.py`: Thompson Sampling _composite
- `queen_runtime.py`: archive_thread tool, define_workflow_steps tool, thread context extension
- `maintenance.py`: contradiction handler, LLM-confirmed dedup extension
- `app.py`: maintenance timer, contradiction handler registration

**Deleted:**
- `surface/skill_lifecycle.py`
- `adapters/skill_dedup.py`
- `frontend/src/components/skill-browser.ts`

### Rollback path

Remove conf_alpha/conf_beta fields from MemoryEntry (backward-compatible, entries revert to flat confidence). Revert composite scoring to `score + status_bonus + confidence * 0.1`. Remove workflow step events and projections. Re-add legacy files from Git history. Event replay will skip unknown event types gracefully.

### Supersedes

- **ADR-010 (Skill crystallization):** Fully superseded. `_crystallize_skills()` has been disabled since Wave 28 and its method body is deleted in Wave 30. Institutional memory extraction is the sole knowledge write path.
- **ADR-017 (Bayesian confidence + LLM dedup):** Partially superseded. The Beta distribution math and LLM dedup pattern are ported to institutional memory. UCB exploration is replaced by Thompson Sampling. The source files (`skill_lifecycle.py`, `skill_dedup.py`) are deleted. The principles of ADR-017 survive; the implementation is replaced.
