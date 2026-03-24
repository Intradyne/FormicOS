# Knowledge System Implementation Reference

Current-state reference for FormicOS institutional memory: entry lifecycle,
Bayesian confidence, Thompson Sampling retrieval, composite scoring, decay,
and maintenance. Code-anchored to Wave 59.

---

## Entry Model

Every knowledge entry is a `MemoryEntry` (Pydantic frozen model, `extra="forbid"`)
defined in `core/types.py`. Persisted as plain dicts on `MemoryEntryCreated` events
for replay safety.

### Identity and Classification

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `str` | — | `mem-{colony_id}-{type[0]}-{index}` |
| `entry_type` | `MemoryEntryType` | — | `skill` or `experience` |
| `sub_type` | `EntrySubType \| None` | `None` | Granular classification (see below) |
| `status` | `MemoryEntryStatus` | `candidate` | Trust lifecycle position |
| `polarity` | `MemoryEntryPolarity` | `positive` | `positive`, `negative`, `neutral` |
| `decay_class` | `DecayClass` | `ephemeral` | Confidence decay rate |

### Sub-types

Skills: `technique`, `pattern`, `anti_pattern`, `trajectory`.
Experiences: `decision`, `convention`, `learning`, `bug`.

`EntrySubType` is a `StrEnum` in `core/types.py`. The `trajectory` sub-type
(Wave 58) stores compressed tool-call sequences in `trajectory_data`:
each dict has `{tool: str, agent_id: str, round_number: int}`.

### Content Fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `title` | `str` | — | Short descriptive title |
| `content` | `str` | — | Full actionable knowledge |
| `summary` | `str` | `""` | One-line for search display |
| `domains` | `list[str]` | `[]` | Domain tags (normalized: lowercase, underscores) |
| `tool_refs` | `list[str]` | `[]` | Tool names referenced |
| `primary_domain` | — | — | Stamped after `model_dump()` (not a model field) |

### Provenance

| Field | Type | Purpose |
|-------|------|---------|
| `source_colony_id` | `str` | Colony that produced this entry |
| `source_artifact_ids` | `list[str]` | Artifact IDs from source colony |
| `source_round` | `int` | Round number of source material |
| `workspace_id` | `str` | Workspace scope |
| `thread_id` | `str` | Thread scope (empty = workspace-wide) |
| `created_at` | `str` | ISO timestamp |
| `playbook_generation` | `str` | Content-hash of playbooks at extraction time |

### Bayesian Confidence

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| `conf_alpha` | `float` | `5.0` | `gt=0` |
| `conf_beta` | `float` | `5.0` | `gt=0` |
| `confidence` | `float` | `0.5` | Initial scalar (legacy display) |
| `scan_status` | `ScanStatus` | `pending` | Security scan result tier |

Default prior: `Beta(5, 5)` — prior strength 10, split evenly. Point estimate
`confidence = alpha / (alpha + beta)`.

---

## Status Lifecycle

```
candidate → verified → stale
    ↓           ↓
  rejected   rejected
```

| Status | Meaning |
|--------|---------|
| `candidate` | Newly extracted, awaiting verification |
| `verified` | Validated by operator or system |
| `rejected` | Explicitly rejected |
| `stale` | Decayed below relevance threshold |

Transitions happen via events: `MemoryEntryStatusChanged`,
`MemoryEntryInvalidated` (operator), `MemoryEntryReinstated` (operator).

---

## Decay Classes

| Class | Gamma (γ) | Half-life | Use |
|-------|-----------|-----------|-----|
| `ephemeral` | 0.98 | ~34 days | Task-specific observations, workarounds |
| `stable` | 0.995 | ~139 days | Domain knowledge, architectural decisions |
| `permanent` | 1.0 | ∞ | Verified definitions, immutable truths |

Gamma-decay is applied at query time, not stored in the CRDT. A 180-day
gamma cap prevents entries from decaying beyond recovery.

### Mastery Restoration

Entries with `decay_class` stable or permanent get a 20% gap-recovery bonus
when re-observed after significant decay (`current_alpha < peak_alpha * 0.5`).
`peak_alpha` is tracked in projections via the `MemoryConfidenceUpdated` handler.

---

## Composite Retrieval Scoring (ADR-044)

Six signals, all normalized to [0, 1]. Default weights defined in
`surface/knowledge_constants.py`:

```python
COMPOSITE_WEIGHTS = {
    "semantic":      0.38,  # vector similarity
    "thompson":      0.25,  # Thompson Sampling exploration score
    "freshness":     0.15,  # exponential decay, 90-day half-life
    "status":        0.10,  # verified=1.0, active=0.8, candidate=0.5, stale=0.0
    "thread":        0.07,  # 1.0 bonus for same-thread entries
    "cooccurrence":  0.05,  # sigmoid: 1 - e^(-0.6w)
}
```

### Signal Details

**Semantic**: Raw vector similarity from Qdrant hybrid search (dense + BM25 + RRF).

**Thompson Sampling**: `exploration_score(alpha, beta, total_observations, ucb_weight)`
from `engine/scoring_math.py`. Draws from `Beta(alpha, beta)` posterior and adds
UCB exploration bonus.

**Freshness**: `2.0^(-age_days / 90.0)` — exponential decay with 90-day half-life.
Computed in `engine/context.py:_compute_freshness()`.

**Status bonus**: `{verified: 1.0, active: 0.8, candidate: 0.5, stale: 0.0}`.
Defined in `surface/knowledge_catalog.py:_STATUS_BONUS`.

**Thread bonus**: Same-thread entries receive `_thread_bonus = 1.0`, weighted at 0.07.
Applied in `KnowledgeCatalog.search()` for thread-scoped retrieval.

**Co-occurrence**: Sigmoid normalization `1 - e^(-0.6w)` where `w` is the raw
co-occurrence weight from the co-occurrence graph. Defined in
`surface/knowledge_catalog.py:_sigmoid_cooccurrence()`.

### Modifiers

**Pin boost**: Pinned entries get retrieval preference via `_pin_boost`.

**Federation penalty**: `federated_retrieval_penalty(item)` from `surface/trust.py`
penalizes weak foreign entries. Uses Bayesian PeerTrust (10th percentile of
Beta posterior). Hop discount: `0.7^hop` with 0.5 cap.

### Per-workspace Weight Overrides (ADR-044 D4)

Workspace-scoped weight overrides via `configure_scoring` MCP tool, stored in
`WorkspaceConfigChanged` events. Falls back to global defaults. At standard/full
retrieval tier, results include `score_breakdown` and `ranking_explanation`.

---

## Retrieval Tiers

Four tiers control how much content is returned per result:

| Tier | Tokens/result | Content |
|------|---------------|---------|
| `summary` | ~15 | Title + one-line summary |
| `standard` | ~75 | Title + summary + preview + domains + decay |
| `full` | ~200+ | Everything including content, Beta params, merge/cluster info |
| `auto` | varies | Starts at summary, escalates if coverage is thin |

Formatting functions in `engine/context.py`: `_format_tiered_catalog_item()`.

---

## Confidence Tiers

Entries are classified into confidence tiers for display (computed in
`engine/context.py:_confidence_tier()`):

| Tier | Criteria |
|------|----------|
| `HIGH` | mean ≥ 0.7 and CI width < 0.20 |
| `MODERATE` | mean ≥ 0.45 |
| `LOW` | mean < 0.45 |
| `EXPLORATORY` | fewer than 3 real observations |
| `STALE` | status == "stale" |

CI width: `1.96 * sqrt(mean * (1 - mean) / (alpha + beta + 1))`.

---

## Extraction Pipeline

### Post-colony Extraction

`surface/memory_extractor.py:build_extraction_prompt()` builds the LLM prompt
for dual skill + experience extraction. Called by `colony_manager.py` after
`ColonyCompleted`/`ColonyFailed`. Fire-and-forget — does not block colony lifecycle.

Extraction modes:
- **Legacy** (no existing entries): Returns `{"skills": [...], "experiences": [...]}`.
- **Curating** (Wave 59, existing entries provided): Returns
  `{"actions": [{type: "CREATE"|"REFINE"|"MERGE"|"NOOP", ...}]}`.

Parameters include `task_class` (Wave 58.5) for `primary_domain` tagging and
`existing_entries` (Wave 59) for curation context.

`primary_domain` is stamped onto entry dicts after `model_dump()` (not a
MemoryEntry field, since the model uses `extra="forbid"`).

### Environment Noise Filtering

`is_environment_noise_text()` filters out entries about workspace configuration,
missing tools, import errors, etc. Uses phrase matching (16 phrases) combined
with context + error pattern matching.

### Transcript Harvest

Second extraction pass on full colony transcript (Wave 33). Classifies turns
as bug, decision, convention, or learning. Maps to `EntrySubType` values.
Called at hook position 4.5 in the post-colony pipeline.

### Security Scanning

5-axis scanning: prompt injection, data exfiltration, credential leakage,
code safety, credential detection (via detect-secrets). See
`surface/credential_scan.py`.

---

## Maintenance Handlers

All registered in `surface/app.py` via `service_router.register_handler()`.

### Deduplication (`make_dedup_handler`)

`surface/maintenance.py`. Finds near-duplicate entries via vector similarity,
asks LLM to merge. Emits `MemoryEntryMerged` events with
`merge_source` ∈ `{"dedup", "federation", "extraction"}`.

### Stale Sweep (`make_stale_sweep_handler`)

Marks entries as stale when confidence drops below threshold.

### Contradiction Detection (`make_contradiction_handler`)

Identifies contradicting entries. Includes `suggested_colony` for auto-dispatch.

### Confidence Reset

Resets priors on entries with excessive prediction errors.

### Curation (`make_curation_handler`, Wave 59)

Selects entries with access ≥ 5 and confidence < 0.65 (popular but unexamined).
Uses `resolve_model("archivist", workspace_id)` for LLM calls. Emits
`MemoryEntryRefined` events with `refinement_source="maintenance"`.

Quality gates: entry exists, `new_content` ≥ 20 chars, content actually changed.

---

## Proactive Intelligence

15 deterministic rules in `surface/proactive_intelligence.py` (no LLM calls):

- 7 knowledge-health rules: confidence decline, contradiction, federation trust
  drop, coverage gap, stale cluster, merge opportunity, federation inbound
- 4 performance rules: strategy efficiency, diminishing rounds, cost outlier,
  knowledge ROI
- Adaptive evaporation signal
- Branching-factor stagnation signal
- Earned-autonomy recommendation

Three rules (contradiction, coverage gap, stale cluster) include
`suggested_colony` configurations for auto-dispatch.

### Distillation

Dense co-occurrence clusters (≥5 entries, avg weight >3.0) are flagged as
distillation candidates. Archivist colonies synthesize into higher-order entries
(`KnowledgeDistilled` event). Distilled entries get `decay_class="stable"` and
elevated alpha (capped at 30).

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/types.py` | MemoryEntry model, all enums |
| `surface/knowledge_catalog.py` | Retrieval, composite scoring, thread boost |
| `surface/knowledge_constants.py` | COMPOSITE_WEIGHTS, workspace overrides |
| `engine/context.py` | Freshness, confidence tiers, tiered formatting |
| `engine/scoring_math.py` | Thompson Sampling exploration_score |
| `surface/memory_extractor.py` | Extraction prompt, parsing, noise filter |
| `surface/maintenance.py` | Dedup, stale sweep, contradiction, curation |
| `surface/proactive_intelligence.py` | 15 deterministic briefing rules |
| `surface/colony_manager.py` | Post-colony extraction orchestration |
| `surface/credential_scan.py` | 5-axis security scanning |
| `surface/trust.py` | Federation penalty, peer trust |
