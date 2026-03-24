# Wave 11 Dispatch -- "The Skill Bank Grows Up"

**Date:** 2026-03-14
**Status:** Draft -- pending orchestrator review
**Depends on:** Wave 10 complete and validated (672 tests, 30/30 smoke gates, 3/4 advisory)
**Exit gate:** Event union expanded (22 -> 27), Beta confidence visible in skill browser,
LLM dedup classifies near-matches, colony spawns from template, Queen names colonies,
suggest-team returns recommendations, multi-step colony creation flow works in browser.
Full `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest` green.
`cd frontend && npm run build` clean.

---

## Read Order (mandatory before writing any code)

1. `CLAUDE.md` -- project rules
2. `AGENTS.md` -- ownership and coordination for THIS wave
3. `docs/decisions/001-event-sourcing.md` -- single mutation path
4. `docs/decisions/010-skill-crystallization.md` -- learning loop
5. `docs/decisions/012-compute-router.md` -- routing architecture
6. `docs/decisions/013-qdrant-migration.md` -- vector store (current)
7. `docs/decisions/014-gemini-provider.md` -- third provider (current)
8. `docs/decisions/015-event-union-expansion.md` -- **NEW -- read carefully before Phase A**
9. `docs/decisions/016-colony-templates.md` -- **NEW -- read before Phase B**
10. `docs/decisions/017-bayesian-confidence-dedup.md` -- **NEW -- read before Phase A T2/T3**
11. `docs/contracts/events.py` -- 22-event union (**MODIFIED IN PHASE A T1**)
12. `docs/contracts/ports.py` -- 5 port interfaces (**MODIFIED IN PHASE A T1 -- EventTypeName only**)
13. `docs/specs/colony_templates.feature` -- executable spec for Phase B
14. `docs/specs/skill_maturity.feature` -- executable spec for Phase A
15. `docs/waves/wave_10/plan.md` -- predecessor wave
16. Current implementations you will modify (see your terminal's file list below)

---

## Two Phases

Wave 11 is two sequential phases, each with 3 parallel coders.

**Phase A -- "Open the Contract + Skill Maturity"**
Opens the event union. Migrates confidence to Beta distribution. Ships two-band dedup with LLM classification. All backend.

**Phase B -- "Templates + Colony Creation + Frontend"**
Colony templates. Queen naming. Suggest-team. Multi-step colony creation UI. Skill browser enhancements. Template browser.

Phase B starts after Phase A merges. Phase B coders build on the new events and confidence infrastructure from Phase A.

---

## Phase A -- Scope Locks

| Terminal | Owns (may modify) | Does NOT touch |
|----------|-------------------|----------------|
| **T1 -- Event Union + Projections** | `core/events.py`, `core/ports.py` (EventTypeName only), `surface/projections.py`, `frontend/src/types.ts`, `frontend/src/events.ts` (if present), contract parity tests | `engine/*`, `adapters/*`, `surface/skill_lifecycle.py`, `surface/colony_manager.py`, `surface/runtime.py`, `config/*` |
| **T2 -- Bayesian Confidence** | `surface/skill_lifecycle.py` (confidence functions only), `surface/colony_manager.py` (SkillConfidenceUpdated emission), `engine/context.py` (UCB in composite scoring), `config/formicos.yaml` (skill_bank section) | `core/events.py`, `core/ports.py`, `frontend/*`, `adapters/*`, `surface/projections.py` |
| **T3 -- LLM Dedup** | new `adapters/skill_dedup.py`, `surface/skill_lifecycle.py` (ingestion functions only -- coordinate with T2), `surface/view_state.py` (skill detail endpoint update) | `core/*`, `engine/*`, `frontend/*`, `surface/projections.py`, `surface/colony_manager.py`, `surface/runtime.py` |

**Merge order: T1 first, then T2 and T3 independently.**

T1 must merge first -- it adds the event types that T2 emits (`SkillConfidenceUpdated`). T2 and T3 modify different functions in `skill_lifecycle.py` (T2 owns confidence update functions, T3 owns ingestion/dedup functions) so they can merge independently after T1.

### T2/T3 coordination on skill_lifecycle.py

T2 owns: `update_skill_confidence()`, `get_skill_bank_summary()`, and any confidence-related helpers.

T3 owns: `validate_skill_for_ingestion()` and calls the new `skill_dedup.classify()` from its own `adapters/skill_dedup.py`.

If the functions are interleaved in the file, T3 should create `adapters/skill_dedup.py` for all dedup logic and only make a surgical call-site change in `skill_lifecycle.py` to invoke it during ingestion.

---

## Phase A -- T1: Event Union Expansion + Projection Handlers

### Goal

Open the 22-event union. Add 4 new event types. Wire projection handlers. Update frontend mirrors.

### ADR prerequisite: Read ADR-015 before starting.

### What changes

**1. `core/events.py`** -- Add 4 event classes:

```python
class ColonyTemplateCreated(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ColonyTemplateCreated"] = "ColonyTemplateCreated"
    template_id: str = Field(..., description="Stable template identifier.")
    name: str = Field(..., description="Human-readable template name.")
    description: str = Field(..., description="Template description.")
    caste_names: list[str] = Field(..., description="Castes included in the template.")
    strategy: CoordinationStrategyName = Field(..., description="Coordination strategy.")
    source_colony_id: str | None = Field(default=None, description="Colony this was saved from.")

class ColonyTemplateUsed(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ColonyTemplateUsed"] = "ColonyTemplateUsed"
    template_id: str = Field(..., description="Template that was used.")
    colony_id: str = Field(..., description="Colony spawned from the template.")

class ColonyNamed(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ColonyNamed"] = "ColonyNamed"
    colony_id: str = Field(..., description="Colony receiving a display name.")
    display_name: str = Field(..., description="Human-readable name assigned by Queen or operator.")
    named_by: str = Field(..., description="Actor: 'queen' or 'operator'.")

class SkillConfidenceUpdated(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["SkillConfidenceUpdated"] = "SkillConfidenceUpdated"
    colony_id: str = Field(..., description="Colony whose completion triggered updates.")
    skills_updated: int = Field(..., ge=0, description="Count of skills with changed confidence.")
    colony_succeeded: bool = Field(..., description="Whether the colony succeeded or failed.")
```

Add all 4 to the `FormicOSEvent` union. Update `__all__`.

**2. `core/ports.py`** -- Extend `EventTypeName` literal with the 4 new type strings.

**3. `surface/projections.py`** -- Add projection handlers:

- `_on_colony_template_created` -> add to a `templates: dict[str, TemplateProjection]` on ProjectionStore
- `_on_colony_template_used` -> increment `use_count` on the template projection
- `_on_colony_named` -> set `display_name` on `ColonyProjection`
- `_on_skill_confidence_updated` -> no projection state change (audit trail event)

Add `display_name: str | None = None` field to `ColonyProjection` if not present. Add `TemplateProjection` model to projections.

**4. `frontend/src/types.ts`** -- Mirror the 4 new event types. Add `display_name?: string` to the Colony type. Add `TemplateInfo` type.

**5. Contract parity tests** -- Update to expect 26 event types (was 22).

### Acceptance criteria

- [ ] 4 new event classes in `core/events.py` following `FrozenConfig` pattern
- [ ] `FormicOSEvent` union contains 26 types
- [ ] `EventTypeName` in `ports.py` lists all 26 type strings
- [ ] Projection handlers wired for all 4 events
- [ ] `ColonyProjection` has `display_name` field
- [ ] `TemplateProjection` model exists in projections
- [ ] Frontend TypeScript mirrors all 4 events
- [ ] Contract parity tests pass (Python <-> TypeScript alignment)
- [ ] All 672+ existing tests pass (new events extend, don't break)
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`
- [ ] `cd frontend && npm run build` clean

### New tests

- `tests/unit/core/test_new_events.py` -- serialize/deserialize round-trip for all 4 events
- `tests/unit/surface/test_projections_w11.py` -- projection handlers for template created/used, colony named, skill confidence updated
- Update existing contract parity test to expect 26 events

---

## Phase A -- T2: Bayesian Confidence Migration

### Goal

Replace flat +/-0.1 confidence with Beta distribution. Add UCB exploration bonus to retrieval scoring. Emit `SkillConfidenceUpdated` events.

### ADR prerequisite: Read ADR-017 before starting.

### What changes

**1. `surface/skill_lifecycle.py`** -- Rewrite confidence functions:

Replace `update_skill_confidence()`:
```python
# OLD: confidence += 0.1 if success else confidence -= 0.1
# NEW: alpha += 1.0 if success, beta += 1.0 if failure
```

Add migration logic:
```python
async def _ensure_beta_fields(vector_port, skill_id, payload):
    """If conf_alpha missing, migrate from flat confidence."""
    if "conf_alpha" not in payload:
        conf = payload.get("confidence", 0.5)
        alpha = conf * 10.0
        beta = (1.0 - conf) * 10.0
        # upsert the new fields
```

Update `get_skill_bank_summary()` to include average uncertainty.

**2. `surface/colony_manager.py`** -- After confidence updates, emit `SkillConfidenceUpdated`:

```python
from formicos.core.events import SkillConfidenceUpdated

# After update_skill_confidence() returns:
await self._runtime.emit_and_broadcast(SkillConfidenceUpdated(
    seq=0, type="SkillConfidenceUpdated", timestamp=utcnow(),
    address=colony_address,
    colony_id=colony_id,
    skills_updated=len(retrieved_skill_ids),
    colony_succeeded=colony_succeeded,
))
```

**3. `engine/context.py`** -- Add UCB exploration bonus to composite scoring:

```python
# Existing:
# composite = 0.50 * semantic + 0.25 * confidence + 0.25 * freshness

# New weights:
n_obs = max(alpha + beta - 2.0, 1.0)  # observations (subtract prior)
exploration = 0.1 * math.sqrt(math.log(max(total_colonies, 1)) / n_obs)
composite = 0.50 * semantic + 0.25 * confidence + 0.20 * freshness + 0.05 * exploration
```

`total_colonies` passed as a parameter to `assemble_context()` -- the caller (colony_manager) knows this from the projection store.

**4. `config/formicos.yaml`** -- Add skill_bank confidence section (optional, for tuning):

```yaml
skill_bank:
  confidence_prior_strength: 10.0   # initial alpha+beta sum for migration
  ucb_exploration_weight: 0.1       # c parameter in UCB formula
  dedup_exact_threshold: 0.98       # Band 1 (T3 uses this too)
  dedup_semantic_threshold: 0.82    # Band 2 lower bound (T3 uses this too)
```

**5. Qdrant payload indexes** -- Add indexes for `conf_alpha` (FLOAT) and `conf_beta` (FLOAT) during migration.

**6. `/api/v1/skills` endpoint update** -- Include `conf_alpha`, `conf_beta`, `uncertainty` in response alongside existing `confidence`.

### Acceptance criteria

- [ ] Skills store `conf_alpha`, `conf_beta`, `conf_last_validated` in Qdrant payload
- [ ] Migration: existing flat confidence -> Beta params on first access
- [ ] Colony success -> alpha += 1.0 for retrieved skills
- [ ] Colony failure -> beta += 1.0 for retrieved skills
- [ ] Derived `confidence` = `alpha / (alpha + beta)` (backward compatible)
- [ ] UCB exploration bonus in composite scoring
- [ ] `SkillConfidenceUpdated` event fires once per colony completion
- [ ] `/api/v1/skills` returns alpha, beta, uncertainty
- [ ] All existing tests pass
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/surface/test_bayesian_confidence.py` -- Beta update on success/failure, migration from flat value, clamping, derived confidence calculation
- `tests/unit/engine/test_ucb_scoring.py` -- UCB bonus for low-observation vs high-observation skills, exploration decay, composite score ordering
- `tests/unit/surface/test_confidence_event.py` -- SkillConfidenceUpdated emission with correct fields

---

## Phase A -- T3: Two-Band Dedup + LLM Classification

### Goal

Replace single cosine > 0.92 gate with two-band system and LLM-gated classification for semantic near-matches.

### ADR prerequisite: Read ADR-017 (Part B) before starting.

### What changes

**1. New file: `adapters/skill_dedup.py`** (~100 LOC)

```python
"""LLM-gated skill deduplication.

Lives in adapters/ because it calls LLMPort (a technology binding).
"""

CLASSIFY_PROMPT = """Compare these two skill descriptions and classify:
EXISTING: {existing}
CANDIDATE: {candidate}

Respond with exactly one word: ADD, UPDATE, or NOOP"""

MERGE_PROMPT = """Combine these two skills into one, preserving all specific details:
SKILL A: {skill_a}
SKILL B: {skill_b}

Write one merged skill description (50-200 words):"""

async def classify(
    llm_port: LLMPort,
    model: str,
    existing_text: str,
    candidate_text: str,
) -> Literal["ADD", "UPDATE", "NOOP"]:
    """LLM classifies relationship between existing and candidate skill."""

async def merge_texts(
    llm_port: LLMPort,
    model: str,
    text_a: str,
    text_b: str,
) -> str:
    """LLM merges two skill texts into one."""
```

Route to `gemini/gemini-2.5-flash` if available, fall back to local model. Temperature 0.0. Max tokens 10 for classify, 300 for merge.

**2. `surface/skill_lifecycle.py`** -- Modify `validate_skill_for_ingestion()`:

Replace:
```python
# OLD: if cosine > 0.92 -> reject
```

With:
```python
# NEW:
# if cosine >= 0.98 -> NOOP (Band 1, no LLM call)
# if cosine in [0.82, 0.98) -> call skill_dedup.classify() (Band 2)
#   ADD -> ingest normally
#   UPDATE -> call skill_dedup.merge_texts(), re-embed, upsert, combine Betas
#   NOOP -> skip
# if cosine < 0.82 -> ingest normally
```

Read thresholds from `config.skill_bank.dedup_exact_threshold` and `config.skill_bank.dedup_semantic_threshold` (T2 adds these to config).

On UPDATE merge, combine Beta distributions:
```python
new_alpha = existing_alpha + candidate_alpha - 1.0
new_beta = existing_beta + candidate_beta - 1.0
```

Emit `SkillMerged` event (if Phase B has already added it -- otherwise structlog only until Phase B).

**3. `surface/view_state.py`** -- Update `get_skill_bank_detail()` to include `merge_count` or `merged_from` in the skill detail response, if tracked in Qdrant payload.

### Acceptance criteria

- [ ] Band 1 (cosine >= 0.98): silently skipped, no LLM call, structlog NOOP
- [ ] Band 2 (cosine [0.82, 0.98)): LLM classification fires
- [ ] Below threshold (cosine < 0.82): ingested normally, no LLM call
- [ ] LLM ADD result: candidate ingested as new skill
- [ ] LLM UPDATE result: texts merged, re-embedded, Betas combined, Qdrant updated
- [ ] LLM NOOP result: candidate skipped, structlog logged
- [ ] Dedup routes to Gemini Flash if available, local fallback
- [ ] Thresholds configurable via formicos.yaml
- [ ] All existing tests pass
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/adapters/test_skill_dedup.py` -- classify returns ADD/UPDATE/NOOP, merge_texts returns combined text, handles LLM failure gracefully
- `tests/unit/surface/test_dedup_bands.py` -- Band 1 exact skip, Band 2 triggers LLM, below threshold ingests, UPDATE combines Betas correctly
- `tests/unit/surface/test_dedup_integration.py` -- end-to-end: candidate with cosine 0.90 -> classify -> UPDATE -> merged skill in Qdrant

---

## Phase B -- Scope Locks

Phase B starts after Phase A merges. Phase B coders have access to all 4 new event types.

| Terminal | Owns (may modify) | Does NOT touch |
|----------|-------------------|----------------|
| **T1 -- Colony Templates Backend** | new `surface/template_manager.py`, `surface/app.py` (REST routes), `core/events.py` (add SkillMerged -- 1 more event), new `config/templates/` directory, tests | `engine/*`, `adapters/*`, `surface/skill_lifecycle.py`, `surface/colony_manager.py`, `frontend/*` |
| **T2 -- Naming + Suggest-Team + Commands** | `surface/queen_runtime.py` (naming), `surface/runtime.py` (suggest-team), `surface/commands.py` (template_id in spawn), `surface/colony_manager.py` (display_name), tests | `core/*`, `engine/*`, `adapters/*`, `frontend/*`, `surface/template_manager.py` |
| **T3 -- Frontend: Creation Flow + Browsers** | All `frontend/src/components/*`, `frontend/src/types.ts`, tests | `core/*`, `engine/*`, `adapters/*`, `surface/*` (backend) |

**Merge order: T1 and T2 independently, T3 last.**

T3 depends on T1 (template REST endpoints) and T2 (suggest-team endpoint, naming WS events) to be merged before it can wire the frontend to them.

### T1/T2 coordination on colony creation path

T1 adds the template loading and `ColonyTemplateUsed` emission logic. T2 extends the spawn command to accept `template_id` and wires Queen naming. They touch different files but the colony creation flow spans both:

- T1 owns `template_manager.py` -- load template, validate, emit `ColonyTemplateCreated`/`ColonyTemplateUsed`
- T2 owns `commands.py` -- accept `template_id` param in spawn command, call template_manager to resolve, then proceed with normal spawn + naming

T2 imports and calls T1's template_manager. T1 merges first or simultaneously -- if simultaneously, T2 stubs the template_manager import until T1 is available.

---

## Phase B -- T1: Colony Templates Backend

### Goal

Implement template storage, REST API, and the SkillMerged event.

### ADR prerequisite: Read ADR-016 before starting.

### What changes

**1. `core/events.py`** -- Add 1 more event (26 -> 27):

```python
class SkillMerged(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["SkillMerged"] = "SkillMerged"
    surviving_skill_id: str = Field(..., description="Skill that absorbed the other.")
    merged_skill_id: str = Field(..., description="Skill that was absorbed.")
    merge_reason: str = Field(..., description="Why merged: 'llm_dedup'.")
```

Add to union. Update `EventTypeName` in `ports.py`. Update frontend mirrors.

**2. New file: `surface/template_manager.py`** (~200 LOC)

- `ColonyTemplate` Pydantic model (see ADR-016)
- `load_templates()` -- read all YAML files from `config/templates/`
- `save_template(template)` -- write YAML, emit `ColonyTemplateCreated`
- `get_template(template_id)` -- load by ID
- `list_templates()` -- return latest version per template_id
- `save_from_colony(colony_projection, runtime)` -- extract config from completed colony, LLM-generate description, save as template

**3. `surface/app.py`** -- REST routes:

```python
# GET /api/v1/templates -- list all
# POST /api/v1/templates -- create template
# GET /api/v1/templates/{id} -- get detail
```

**4. `config/templates/`** -- Create directory. Add one example template:

```yaml
# config/templates/code-review.yaml
template_id: "builtin-code-review"
name: "Code Review"
description: "Coder + Reviewer pair for implementation and quality review."
version: 1
caste_names: ["coder", "reviewer"]
strategy: "stigmergic"
budget_limit: 1.0
max_rounds: 15
tags: ["code", "review"]
created_at: "2026-03-14T00:00:00Z"
use_count: 0
```

**5. `surface/projections.py`** -- Add handler for `SkillMerged` (audit trail, no state change needed beyond logging).

### Acceptance criteria

- [ ] `SkillMerged` event added to union (27 total)
- [ ] Template YAML files load correctly
- [ ] `POST /api/v1/templates` creates a YAML file and emits `ColonyTemplateCreated`
- [ ] `GET /api/v1/templates` returns template list
- [ ] Template versioning: edit creates new version, old retained
- [ ] `save_from_colony()` generates description via LLM
- [ ] Example template included in `config/templates/`
- [ ] All tests pass
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/surface/test_template_manager.py` -- load, save, list, versioning, save-from-colony
- `tests/unit/core/test_skill_merged_event.py` -- serialize/deserialize
- `tests/unit/surface/test_template_endpoints.py` -- REST GET/POST

---

## Phase B -- T2: Queen Naming + Suggest-Team + Spawn Extension

### Goal

Colonies get human-readable names. Operators get team suggestions. Spawn accepts template_id.

### ADR prerequisite: Read ADR-016 (naming + suggest-team sections).

### What changes

**1. `surface/queen_runtime.py`** -- Queen naming after colony creation:

```python
async def _name_colony(self, colony_id: str, task: str) -> str | None:
    """Generate a display name for a newly spawned colony."""
    prompt = f"Generate a short, memorable project name (2-4 words, no quotes) for: {task}"
    try:
        # Route to Gemini Flash (cheap), local fallback
        response = await asyncio.wait_for(
            self._llm_port.complete(
                model="gemini/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=20,
            ),
            timeout=0.5,  # 500ms hard timeout
        )
        name = response.content.strip().strip('"\'')
        if 1 < len(name) < 50:
            return name
    except Exception:
        pass
    return None  # fallback to colony-{uuid[:8]}
```

After naming, emit `ColonyNamed` event.

**2. `surface/runtime.py`** -- Suggest-team method:

```python
async def suggest_team(self, objective: str) -> list[dict]:
    """LLM recommends castes for a given objective."""
    castes_desc = "\n".join(f"- {name}: {c.description}" for name, c in self._castes.items())
    prompt = f"""Given this objective, recommend which castes to include.
Available castes:
{castes_desc}

Objective: {objective}

Respond as JSON array: [{{"caste": "name", "count": 1, "reasoning": "why"}}]"""
    # Route to Gemini Flash, local fallback. Temperature 0.0.
```

Wire as `POST /api/v1/suggest-team` in app.py and as a WS command.

**3. `surface/commands.py`** -- Extend spawn colony command to accept optional `template_id`:

```python
# When template_id is provided:
# 1. Load template via template_manager
# 2. Use template's castes/strategy/budget as defaults
# 3. Override with any explicitly provided fields
# 4. Emit ColonyTemplateUsed event
# 5. Proceed with normal spawn
```

**4. `surface/colony_manager.py`** -- Add `display_name` to colony tracking:

After colony spawn, call `queen_runtime._name_colony()`. Store result. If naming succeeds, emit `ColonyNamed`. If fails, leave display_name as None (frontend shows UUID).

### Acceptance criteria

- [ ] New colony gets Queen-assigned display_name within 2 seconds
- [ ] Naming timeout (500ms) -> fallback to None, no error
- [ ] `ColonyNamed` event emitted on successful naming
- [ ] `POST /api/v1/suggest-team` returns caste recommendations
- [ ] Suggest-team routes to Gemini Flash if available, local fallback
- [ ] Spawn command accepts `template_id`, loads template, applies defaults
- [ ] `ColonyTemplateUsed` emitted when template used
- [ ] All tests pass

### New tests

- `tests/unit/surface/test_queen_naming.py` -- naming success, timeout fallback, empty response handling
- `tests/unit/surface/test_suggest_team.py` -- returns valid castes, handles LLM failure
- `tests/unit/surface/test_spawn_with_template.py` -- template defaults applied, overrides work, event emitted

---

## Phase B -- T3: Frontend -- Colony Creation + Skill Browser + Template Browser

### Goal

Multi-step colony creation flow. Skill browser shows Beta confidence and merge badges. Template browser with save-as-template.

### Depends on: T1 + T2 merged

Delegate to 3 parallel sub-agents:

### Sub-agent A -- Colony creation flow (~300 LOC)

The current single-step spawn becomes a multi-step experience:

**Step 1: Describe.** Text input for objective. On submit, fire two parallel requests:
- `POST /api/v1/suggest-team` -> shows recommended castes
- `GET /api/v1/templates` -> shows matching templates (filter by tag or name similarity)

Display: suggested team as the default config, templates as "or start from a saved template" cards below.

**Step 2: Configure.** Shows the selected caste list (from suggestion or template). Each caste shows the resolved model from the routing table. The operator can:
- Add/remove castes
- Adjust budget (default from workspace config)
- If a template was selected, show "from {template_name}" badge

**Step 3: Launch.** Confirm button. Colony creates via existing WS command (now with optional `template_id`). Name shimmer -> fills via `ColonyNamed` WebSocket event. Auto-navigate to colony detail (Wave 10 fix).

### Sub-agent B -- Skill browser enhancements (~100 LOC)

Update the existing `skill-browser.ts` to show:
- Confidence as mean +/- uncertainty bar (narrow = well-established, wide = uncertain)
- `conf_alpha` and `conf_beta` visible on hover/tooltip
- "Merged" badge on skills that went through UPDATE dedup
- Color coding: green (high confidence, low uncertainty), amber (moderate), red (low confidence or high uncertainty)

Update `GET /api/v1/skills` types to include `conf_alpha`, `conf_beta`, `uncertainty`.

### Sub-agent C -- Template browser + colony card polish (~200 LOC)

- **Template browser:** List view accessible from colony creation Step 1 and as standalone section in Queen Overview. Shows: name, description, caste tags, use count, source colony link.
- **"Save as template" button** on completed colony detail -- calls `POST /api/v1/templates` with colony config.
- **Colony cards:** Show `display_name` prominently (larger font). UUID as subtitle/tooltip. Fallback display when no name assigned yet.
- **Routing badges** in colony detail: show actual model name per agent (e.g., "gemini-2.5-flash" not just "cloud").

### Acceptance criteria

- [ ] Colony creation: 3-step flow works end-to-end
- [ ] Suggest-team results populate Step 2 castes
- [ ] Template selection populates Step 2 with template config
- [ ] Colony name shimmer -> fills via ColonyNamed event
- [ ] Skill browser shows +/- uncertainty bars
- [ ] Skill browser shows merge badges
- [ ] Template browser lists templates with use counts
- [ ] "Save as template" button works on completed colony detail
- [ ] Colony cards show display_name prominently
- [ ] TypeScript compiles clean (`npm run build`)
- [ ] No console errors in browser

### New tests

- Frontend: `npm run build` + manual browser verification

---

## Data Provenance Table

| Datum | Source | Persisted? | Survives restart? |
|-------|--------|-----------|-------------------|
| `conf_alpha`, `conf_beta` | Migrated from flat confidence, then updated by skill_lifecycle.py | Qdrant payload | Yes |
| `conf_last_validated` | Set on each confidence update | Qdrant payload | Yes |
| Derived `confidence` | `alpha / (alpha + beta)`, computed on update | Qdrant payload | Yes |
| UCB exploration bonus | Computed at retrieval time from alpha+beta+total_colonies | Not persisted | N/A |
| LLM dedup classification | Returned by skill_dedup.classify() | Not persisted (structlog only) | No |
| Merged skill text | LLM merge result, stored via Qdrant upsert | Qdrant payload | Yes |
| Colony display_name | Queen LLM call result, stored via ColonyNamed event -> projection | Event store + projection | Yes (replayed) |
| Template YAML files | Written to `config/templates/` | Filesystem | Yes |
| Template use_count | Derived from ColonyTemplateUsed events in projection | Projection (replayed) | Yes |
| Suggest-team result | LLM call, returned to frontend | Not persisted | No |

---

## Integration Gate

After both phases complete:

```bash
# Full CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build

# Docker smoke
docker compose build formicos && docker compose up -d
sleep 15 && curl http://localhost:8080/health

# Phase A validation
# 1. Event union: 27 event types in the union (was 22)
# 2. Confidence: /api/v1/skills returns conf_alpha, conf_beta, uncertainty
# 3. Dedup Band 1: duplicate skill (cosine 0.99) silently skipped
# 4. Dedup Band 2: near-match (cosine 0.90) triggers LLM classification
# 5. Dedup UPDATE: merged skill appears in skill browser with badge

# Phase B validation
# 1. POST /api/v1/templates creates YAML in config/templates/
# 2. Colony spawned with template_id emits ColonyTemplateUsed
# 3. New colony gets display_name within 2 seconds (or falls back gracefully)
# 4. POST /api/v1/suggest-team returns caste recommendations
# 5. Multi-step colony creation flow works in browser
# 6. Colony cards show display_name prominently
# 7. Skill browser shows +/- uncertainty bars
# 8. Template browser lists templates with "Save as template" from colony detail
```

---

## Explicit Deferrals (NOT in Wave 11)

| Deferred | Why | Earliest |
|----------|-----|----------|
| HDBSCAN batch consolidation | 0 new deps > 3 heavy deps. < 100 skills. | Wave 12+ (500+ skills) |
| Meta-skill synthesis | Needs clusters that don't exist | Wave 12+ |
| SGLang inference swap | Pending benchmark sprint | Wave 12 (conditional) |
| Knowledge graph | No consumer beyond stall detection | Wave 12 |
| Embedding model upgrade | Not blocking at < 1K skills | Wave 12 |
| Hybrid search (BM25 + dense) | Overkill at < 1K entries | Wave 12+ |
| Experimentation engine | Needs production data this wave generates | Wave 13+ |
| Dashboard composition | Needs more components + frontend maturity | Wave 13+ |
| Remove LanceDB from pyproject.toml | Keep fallback one more wave | Wave 12 |

---

## Constraints

1. **Contract opens in Phase A T1 only.** 4 events in Phase A, 1 in Phase B T1. Total: 27.
2. **No new dependencies.** Beta math uses stdlib. LLM dedup uses existing adapters. Templates use existing pyyaml.
3. **Pydantic v2 only.** structlog only. No print(). Layer boundaries enforced.
4. **Merge order.** Phase A: T1 first, then T2+T3 independently. Phase B: T1+T2 independently, T3 last.
5. **No hidden state.** Every datum has documented provenance.
6. **Tests required.** Every behavioral change needs a test.
7. **ADR-015, ADR-016, ADR-017 read before coding starts.**
