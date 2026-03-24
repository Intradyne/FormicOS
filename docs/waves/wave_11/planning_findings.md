# Wave 11 Planning Findings -- "The Skill Bank Grows Up"

**Date:** 2026-03-14
**Input:** Wave 10 "Real Infrastructure" implementation largely complete (672 tests, pending Docker smoke)
**Input:** Wave 11 rough outline reviewed and critiqued
**Purpose:** Architecture-aware findings to finalize the Wave 11 plan once Wave 10 is validated

---

## 1. What We Learned from Waves 8--10

### The system is real now

Waves 8--10 built a complete feedback loop on real infrastructure:

- **Wave 8** closed the loop: agents do work -> skills crystallize -> quality scores -> cost tracks.
- **Wave 9** made it smart: routing is config-driven and budget-aware, skills have confidence and freshness, observation hooks produce data exhaust.
- **Wave 10** made it real: Qdrant replaced LanceDB (payload filtering, tenant indexing), Gemini is the third provider (7x cheaper than Claude for bulk work), defensive parsing hardens all three providers, and the frontend has a skill browser.

The combined result: FormicOS now has **672 tests**, **~5,000+ Python source LOC** (well under the 15K limit with ~10K headroom), **14 runtime dependencies**, **3 LLM providers**, a **production vector store**, and a **browsable skill surface**. The system runs real colonies that produce real skills that are retrieved by real routing decisions.

### What's missing is not infrastructure -- it's lifecycle and reusability

The system can run colonies and accumulate skills. What it cannot do:

1. **Manage skills with statistical rigor.** Confidence is +/-0.1 clamped to [0.1, 1.0]. A skill used twice looks the same as one used 200 times. No uncertainty measurement. No exploration bonus.

2. **Handle duplicates intelligently.** Cosine > 0.92 rejects near-exact matches at ingestion time. But skills that express the same concept in different words accumulate. No LLM-gated classification, no batch consolidation.

3. **Reuse colony configurations.** Every colony is created from scratch. No templates, no "do what worked last time." The suggest-team endpoint exists in concept (README mentions it) but has no implementation or UI.

4. **Give colonies meaningful identity.** Colonies are `colony-{uuid}`. No names, no descriptions, no way to distinguish "the auth refactor" from "the test migration" at a glance.

5. **Expose subcaste tiers to the operator.** The caste_recipes.yaml defines castes but there's no subcaste tier system (heavy/balanced/light). The operator can't see or control which capability tier each agent gets.

### What Wave 10 specifically unlocked for Wave 11

**Qdrant payload filtering enables smarter skill operations.** Before W10, every skill query was a flat semantic search. Now the adapter supports payload-filtered queries -- confidence ranges, source colony exclusion, algorithm version selection, namespace isolation. Wave 11's confidence migration and dedup pipeline can leverage these filters directly without post-processing.

**Three-provider routing makes Queen naming and suggest-team cheap.** Queen naming is a single LLM call. The suggest-team endpoint is a single LLM call. Both can route to Gemini Flash ($0.30/M input) or even local Qwen3, making them effectively free. Before W10, these would have consumed expensive Claude tokens.

**The skill browser provides an immediate surface for skill lifecycle improvements.** Any confidence display changes, dedup indicators, or synthesis badges have a ready-made rendering target. The `/api/v1/skills` endpoint is extensible.

**672 tests and ~10K LOC headroom mean Wave 11 can be ambitious.** The contract has been frozen for 10 waves. Opening it is a big decision, but the test suite provides a safety net -- every event consumer has tests that will break if the new events are wired incorrectly.

---

## 2. What Wave 10 Limitations Mean for Wave 11

### Skill confidence is metadata, not event-sourced

Skill confidence lives as a mutable field in Qdrant point payloads. `skill_lifecycle.py` updates it via `vector_port.upsert()`. This is not replayed on restart -- it's best-effort state. Wave 11 can either:

- **Lean in:** Keep confidence as mutable vector-store metadata. Add Beta distribution fields (`conf_alpha`, `conf_beta`, `conf_last_validated`) alongside the existing `confidence` field. This is simpler and matches the current pattern.
- **Promote to events:** Add `SkillConfidenceUpdated` events so confidence changes are event-sourced and replayable. This is cleaner architecturally but creates high-frequency events (every colony completion updates multiple skills).

**Recommendation: Lean in for now, with one event for visibility.** Keep confidence as Qdrant metadata (fast, fire-and-forget). Add a single `SkillConfidenceUpdated` event that fires once per colony completion with a summary of all confidence changes. This gives the event store an audit trail without drowning it in per-skill events.

### Colony creation is surface-layer, not engine-layer

Colony creation is wired through `Runtime.spawn_colony()` in the surface layer. Templates, naming, and suggest-team are all surface-layer features -- they don't touch the engine or core. This means Wave 11's colony creation overhaul can be fully contained in `surface/` and `frontend/` without risking engine stability.

### The event union has been frozen since Phase 2

10 waves of development without touching `core/events.py`. The 22-event union is the most stable artifact in the codebase. Opening it is the right call for Wave 11, but the scope must be disciplined:

**Events that need to exist (Wave 11 emits them):**
- `ColonyTemplateCreated` -- template saved, needs to appear in projections
- `ColonyTemplateUsed` -- template selected for colony creation, audit trail
- `ColonyNamed` -- Queen assigns a name, frontend updates reactively
- `SkillConfidenceUpdated` -- batch confidence change summary per colony completion

**Events that do NOT need to exist yet (nothing emits them):**
- `SkillAdded` -- `ColonyCompleted.skills_extracted` already tracks this; Qdrant upsert is sufficient
- `SkillDecayed` -- no decay job exists yet; add the event when the job ships
- `SkillMerged` -- only needed when LLM-gated dedup ships (Wave 11 Phase B)
- `SkillSynthesized` -- only needed when synthesis ships; defer to when the feature is real
- `ColonyTemplateDeprecated` -- speculative; no deprecation mechanism exists

**Revised count: 4 new events in Phase A, 1 more in Phase B** (SkillMerged, if LLM dedup ships). This is a 23% expansion of the union (22 -> 26 or 27), not the 41% (22 -> 31) from the original outline.

### Queen tool-calling on local models remains advisory

Wave 9 and 10 didn't fix this -- it's a model capability limitation. Wave 11's Queen naming and suggest-team features should use Gemini Flash as the primary model for these calls, with local as fallback. The routing table already supports this pattern.

---

## 3. Recommended Wave 11 Shape

### Theme: "The Skill Bank Grows Up"

Two phases, not three. The original outline had three phases (A: contract + confidence, B: templates + dedup + synthesis, C: frontend). This is too spread out. Consolidate:

**Phase A -- "Open the Contract + Skill Maturity"** (3 coders, sequential merge)

Opens the event union. Migrates confidence to Beta distribution. Adds two-band dedup threshold. Ships all backend changes.

**Phase B -- "Templates + Colony Creation + Frontend"** (3 coders, parallel merge)

Colony templates. Queen naming. Suggest-team wiring. Colony creation flow overhaul. Skill browser enhancements. Template browser.

### What was cut from the original outline

| Cut | Why | When it returns |
|-----|-----|-----------------|
| HDBSCAN batch consolidation | 3 new heavy deps (hdbscan, umap-learn, scipy/numba). < 100 skills. Overkill. | Wave 12+ when bank reaches 500+ |
| Meta-skill synthesis | Needs skill clusters that don't exist yet. | Wave 12+ after HDBSCAN ships |
| 5 speculative events | Nothing emits them. Add when the feature ships. | Per-feature |
| `SkillAdded` event | `ColonyCompleted.skills_extracted` already tracks; Qdrant upsert is the store | Probably never -- the current pattern works |
| `ColonyTemplateDeprecated` event | No deprecation mechanism exists | When someone builds deprecation |

### What was refined

| Original | Revised | Why |
|----------|---------|-----|
| 9 new event types in Phase A | 4 in Phase A, 1 in Phase B | Only add events that are immediately emitted |
| LLM-gated dedup as separate Phase B T1 | Folded into Phase A T3 as the natural extension of the threshold change | Keeps dedup work together |
| Suggest-team as a sub-item of T2 | Elevated to a first-class Phase B deliverable | It's the most impactful operator UX change |
| Skill synthesis via HDBSCAN | Cut entirely | Wrong tool for the current scale |

---

## 4. Proposed Phase A -- "Open the Contract + Skill Maturity"

### New events (4 total)

```python
class ColonyTemplateCreated(EventEnvelope):
    type: Literal["ColonyTemplateCreated"] = "ColonyTemplateCreated"
    template_id: str
    name: str
    description: str
    caste_names: list[str]
    strategy: CoordinationStrategyName
    source_colony_id: str | None = None  # if saved from a completed colony

class ColonyTemplateUsed(EventEnvelope):
    type: Literal["ColonyTemplateUsed"] = "ColonyTemplateUsed"
    template_id: str
    colony_id: str  # the colony that was spawned from this template

class ColonyNamed(EventEnvelope):
    type: Literal["ColonyNamed"] = "ColonyNamed"
    colony_id: str
    display_name: str
    named_by: str  # "queen" or "operator"

class SkillConfidenceUpdated(EventEnvelope):
    type: Literal["SkillConfidenceUpdated"] = "SkillConfidenceUpdated"
    colony_id: str  # the colony whose completion triggered updates
    skills_updated: int  # count of skills whose confidence changed
    colony_succeeded: bool  # success or failure triggered the update
```

These events are immediately emitted by features in Phase A (T1 adds events, T2 emits SkillConfidenceUpdated, T3 doesn't need them yet) and Phase B (T2 emits ColonyTemplateCreated, ColonyTemplateUsed, ColonyNamed).

### T1 -- Event union expansion + projection handlers

**Owns:** `core/events.py`, `core/ports.py` (add ColonyNamed to EventTypeName), `surface/projections.py` (handlers for 4 new events), `frontend/src/types.ts` (mirror), `frontend/src/events.ts` (mirror)

Merge first. Every other terminal depends on the new event types.

Work:
- Add 4 event classes to `core/events.py`
- Extend `FormicOSEvent` union (22 -> 26)
- Update `EventTypeName` literal in `ports.py`
- Add projection handlers (ColonyNamed -> update `ColonyProjection.display_name`, ColonyTemplateCreated -> add to a `templates` dict in ProjectionStore, etc.)
- Update frontend TypeScript mirrors
- Update contract parity tests
- Run full CI -- all 672+ existing tests must pass with the expanded union

### T2 -- Bayesian confidence migration

**Owns:** `surface/skill_lifecycle.py`, `surface/colony_manager.py` (SkillConfidenceUpdated emission), `config/formicos.yaml` (skill_bank section for confidence params)

Work:
- Add `conf_alpha`, `conf_beta`, `conf_last_validated` payload fields to Qdrant skill documents
- Migration: existing `confidence` value -> `alpha = conf * 10, beta = (1 - conf) * 10`
- Create Qdrant payload indexes for new fields
- Replace flat +/-0.1 update with Beta distribution: `alpha += weight` on success, `beta += weight` on failure
- `confidence` field becomes derived: `alpha / (alpha + beta)` -- backward compatible with existing retrieval
- Add UCB exploration bonus to composite scoring: `score + c * sqrt(ln(N) / n_i)` where `n_i = alpha + beta - 2` (number of observations) and `N = total colony count`
- Emit `SkillConfidenceUpdated` event after batch update (one event per colony completion, not per skill)
- Update `/api/v1/skills` endpoint to include alpha, beta, uncertainty in response

### T3 -- Two-band dedup + LLM classification

**Owns:** `surface/skill_lifecycle.py` (dedup functions -- coordinate with T2 on this file), new `adapters/skill_dedup.py` if separation needed

Work:
- Replace single cosine > 0.92 threshold with two bands:
  - **Band 1 (cosine >= 0.98):** NOOP -- near-identical, silently skip
  - **Band 2 (cosine in [0.82, 0.98)):** LLM classification
- LLM classification prompt (Gemini Flash or local, temperature 0.0):
  ```
  Compare these two skill descriptions and classify:
  EXISTING: {existing_skill_text}
  CANDIDATE: {new_skill_text}
  
  Respond with exactly one word: ADD, UPDATE, or NOOP
  - ADD: candidate contains genuinely new information
  - UPDATE: candidate improves or extends the existing skill
  - NOOP: candidate is redundant with existing skill
  ```
- On UPDATE: merge texts via a second LLM call, re-embed, update Qdrant point. Combine Beta distributions: `new_alpha = old_alpha + candidate_alpha - 1, new_beta = old_beta + candidate_beta - 1`. If Phase B adds `SkillMerged` event, emit it; otherwise structlog only.
- On NOOP: silently skip (existing behavior but with LLM verification)
- On ADD: ingest normally (existing behavior)
- Cost: ~1 LLM call per near-match at ingestion time. Gemini Flash at $0.30/M = negligible.

**T2/T3 coordination on `skill_lifecycle.py`:** T2 owns the confidence update functions. T3 owns the dedup/ingestion functions. These are different functions in the same file. Define ownership at the function level, not the file level. Or: T3 creates a new `adapters/skill_dedup.py` for the dedup logic and `skill_lifecycle.py` calls it.

**Merge order: T1 first (events), then T2 and T3 can merge independently** (they modify different functions in `skill_lifecycle.py`, or T3 creates a separate file).

---

## 5. Proposed Phase B -- "Templates + Colony Creation + Frontend"

### Additional event (1 total)

```python
class SkillMerged(EventEnvelope):
    type: Literal["SkillMerged"] = "SkillMerged"
    surviving_skill_id: str
    merged_skill_id: str  # the skill that was absorbed
    merge_reason: str  # "llm_dedup" or "batch_consolidation"
```

Added to the union in Phase B T1. Total union size: 22 -> 27.

### T1 -- Colony templates backend

**Owns:** new `surface/template_manager.py`, `surface/app.py` (REST routes), `config/` (templates directory)

Work:
- `ColonyTemplate` Pydantic model: `template_id`, `name`, `description`, `caste_names`, `strategy`, `model_overrides`, `budget_limit`, `max_rounds`, `version`, `created_at`, `source_colony_id`, `use_count`, `tags`
- Storage: YAML files in `config/templates/`. Git-trackable, human-editable. No database.
- REST endpoints:
  - `GET /api/v1/templates` -- list all templates
  - `POST /api/v1/templates` -- create template (manual or from colony)
  - `GET /api/v1/templates/{id}` -- get template detail
- Extend `POST /api/v1/colonies` (or the WS `spawn_colony` command) to accept `template_id`. When present, colony spawns with template's caste/strategy/budget config. Operator can override individual fields.
- Immutable versioning: editing a template creates a new version, old version retained.
- Emit `ColonyTemplateCreated` on save, `ColonyTemplateUsed` on spawn.
- "Save as template" logic: takes a `ColonyCompleted` event's colony projection, extracts config, generates description via LLM call, saves as template.
- Also add `SkillMerged` event to `core/events.py` in this terminal (extends T1's Phase A work).

### T2 -- Queen naming + suggest-team + colony creation commands

**Owns:** `surface/queen_runtime.py` (naming), `surface/runtime.py` (suggest-team), `surface/commands.py` (creation flow), `surface/colony_manager.py` (display_name field)

Work:
- **Queen naming.** After colony creation, fire a single LLM call (route to Gemini Flash, temperature 0.3, max_tokens 20):
  ```
  Generate a short, memorable project name (2-4 words, no quotes) for a colony working on: {task_objective}
  ```
  Store on `ColonyProjection.display_name`. Emit `ColonyNamed` event. Fallback: if LLM fails or times out (500ms), keep the existing `colony-{uuid[:8]}` name. The name is cosmetic -- routing, events, and correlation always use the UUID.
- **Suggest-team endpoint.** `POST /api/v1/suggest-team`:
  ```json
  Request:  {"objective": "Refactor the auth module to use JWT"}
  Response: {"castes": [
    {"caste": "coder", "count": 1, "reasoning": "Implementation needed"},
    {"caste": "reviewer", "count": 1, "reasoning": "Code quality gate"},
    {"caste": "researcher", "count": 1, "reasoning": "JWT best practices lookup"}
  ]}
  ```
  Single LLM call with the objective + available castes from `caste_recipes.yaml`. Route to Gemini Flash (cheap) with local fallback. Temperature 0.0 for deterministic suggestions.
- Wire suggest-team into WS commands so the frontend can call it without a separate REST fetch.

### T3 -- Frontend: colony creation flow + skill browser + template browser

**Owns:** All `frontend/src/components/*`, `frontend/src/types.ts`

Delegate to 3 parallel sub-agents:

**Sub-agent A -- Colony creation flow overhaul** (~300 LOC)

The current "New Colony" experience becomes multi-step:

- **Step 1: Describe.** Text input for objective. On submit, two parallel calls: `POST /api/v1/suggest-team` (returns recommended castes) and `GET /api/v1/templates` (returns matching templates). Show both -- suggested team as default, templates as "or start from a saved template."
- **Step 2: Configure.** Show caste list with add/remove controls. Each caste shows the resolved model from the routing table. If a template was selected, show "from {template_name}" badge. Budget input with default from workspace config.
- **Step 3: Launch.** Confirm button. Colony creates. Name shimmer -> fills via `ColonyNamed` WebSocket event (~1 second). Auto-navigate to colony detail.

**Sub-agent B -- Skill browser enhancements** (~100 LOC)

Update skill browser to show:
- Confidence as mean +/- uncertainty (from `conf_alpha`/`conf_beta`)
- Colored uncertainty bar (narrow = well-established, wide = uncertain)
- "Merged from N skills" badge for UPDATE-merged entries
- Dedup indicator on recently-classified skills

**Sub-agent C -- Template browser + colony card polish** (~200 LOC)

- Template browser: list view with name, description, caste tags, use count. Accessible from colony creation Step 1 and as standalone view.
- "Save as template" button on completed colony detail -- calls `POST /api/v1/templates` with colony config.
- Colony cards: show Queen-assigned `display_name` prominently, UUID as subtitle/tooltip.
- Routing badges in colony detail show the actual model name per agent (e.g., "gemini-2.5-flash" not just "cloud").

**All three sub-agents merge independently** -- they modify different component files.

---

## 6. Contract Change Summary

### Phase A opens the union from 22 -> 26 events

| New Event | Emitter | Projection Effect |
|-----------|---------|-------------------|
| `ColonyTemplateCreated` | `template_manager.py` on save | Adds to `ProjectionStore.templates` dict |
| `ColonyTemplateUsed` | `template_manager.py` on spawn | Increments template `use_count` in projection |
| `ColonyNamed` | `queen_runtime.py` after spawn | Sets `ColonyProjection.display_name` |
| `SkillConfidenceUpdated` | `colony_manager.py` on colony completion | Audit trail only (confidence lives in Qdrant) |

### Phase B adds 1 more -> 27 events

| New Event | Emitter | Projection Effect |
|-----------|---------|-------------------|
| `SkillMerged` | `skill_dedup.py` on LLM-gated UPDATE | Audit trail (merge history for skill browser) |

### What stays out

| NOT added | Reason |
|-----------|--------|
| `SkillAdded` | `ColonyCompleted.skills_extracted` + Qdrant upsert is sufficient |
| `SkillDecayed` | No decay job exists. Add when it ships. |
| `SkillSynthesized` | No synthesis exists. Add when it ships. |
| `ColonyTemplateDeprecated` | No deprecation mechanism. Speculative. |

---

## 7. Dependency Impact

### Phase A: No new dependencies

Beta distribution uses `math.lgamma()` from stdlib. No scipy needed for the PPF at alpha scale -- the `alpha / (alpha + beta)` point estimate and `(a*b) / ((a+b)^2 * (a+b+1))` variance formula are pure arithmetic.

### Phase B: No new dependencies

Templates are YAML files parsed with `pyyaml` (already a dependency). LLM calls for naming and suggest-team use existing adapters. No HDBSCAN, no UMAP, no scipy.

**Total new Wave 11 dependencies: 0.**

This is a significant improvement over the original outline which proposed 3 heavy deps.

---

## 8. LOC Budget Check

Current: ~5,000+ Python source LOC (post-W10)
Budget: 15,000 LOC hard limit
Headroom: ~10,000 LOC

Wave 11 estimated additions:
- Phase A: ~400 LOC (4 events + projection handlers + confidence migration + dedup bands + LLM classify)
- Phase B: ~600 LOC (template_manager + naming + suggest-team + REST routes + 1 event)
- Frontend: ~600 LOC (colony creation flow + skill browser enhancements + template browser)

Total: ~1,600 LOC -> ~6,600 post-W11. Comfortable headroom of ~8,400.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Opening the event union breaks existing consumers | Low | High | 672 tests catch every handler. Add events to union + projection handlers in one atomic merge. |
| LLM dedup classification is unreliable on local model | Medium | Low | Route to Gemini Flash (cheap, reliable). Local as fallback. Classification is ADD/UPDATE/NOOP -- simple enough for any model. |
| Queen naming times out or returns garbage | Medium | Low | 500ms timeout, fallback to UUID name. Name is cosmetic -- never in routing or correlation. |
| Template storage as YAML files doesn't scale | Low | Low | At alpha scale (<100 templates), YAML is fine. Migrate to SQLite if needed, but probably never. |
| T2/T3 file conflict on skill_lifecycle.py | Medium | Medium | T3 creates `adapters/skill_dedup.py` for dedup logic. T2 owns confidence functions. Clean separation. |
| Frontend colony creation flow is complex for one terminal | Medium | Medium | Split across 3 sub-agents with different component files. Integration is at the WS message level, not code imports. |

---

## 10. Exit Gate

```bash
# Full CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build

# Docker smoke
docker compose build formicos && docker compose up -d
sleep 15 && curl http://localhost:8080/health

# Phase A validation
# 1. Event union: 26+ event types parse/serialize correctly
# 2. Confidence: skill with alpha=5 beta=2 shows confidence 0.71 in browser
# 3. Dedup: near-duplicate skill (cosine 0.90) triggers LLM classification
# 4. Dedup: exact duplicate (cosine 0.99) is silently skipped

# Phase B validation
# 1. Templates: POST /api/v1/templates creates a template YAML in config/templates/
# 2. Templates: colony spawned with template_id emits ColonyTemplateUsed event
# 3. Naming: new colony gets a Queen-assigned display_name within 2 seconds
# 4. Suggest-team: POST /api/v1/suggest-team returns reasonable caste recommendations
# 5. Creation flow: multi-step colony creation works end-to-end in browser
# 6. Colony card: shows display_name prominently, UUID as subtitle
# 7. Skill browser: shows confidence +/- uncertainty, merge badges
# 8. Template browser: lists templates, "Save as template" works from colony detail
```

---

## 11. What Comes After Wave 11

| Feature | Wave | Rationale |
|---------|------|-----------|
| HDBSCAN batch consolidation | 12 | Needs 500+ skills. Zero-dep alternative (cosine clustering) could come sooner. |
| Meta-skill synthesis | 12 | Needs clusters from HDBSCAN or simpler alternative |
| Inference benchmark sprint | Pre-12 | Gate SGLang/vLLM decision on real data |
| SGLang inference swap | 12 (conditional) | Only if benchmark passes threshold |
| Knowledge graph (SQLite adjacency) | 12 | Archivist TKG tuples accumulate now; graph stores them durably |
| Embedding model upgrade (Qwen3-Embedding) | 12 | Coordinate with collection migration |
| Hybrid search (BM25 + dense) | 12 | Requires Qdrant named vectors, coordinate with embedding upgrade |
| Experimentation Engine | 13+ | Needs production data from routing + templates + skill lifecycle |
| Dashboard composition (A2UI) | 13+ | Needs stable component inventory + template system |
