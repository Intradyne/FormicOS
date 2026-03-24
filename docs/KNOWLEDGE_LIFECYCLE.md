# Knowledge Lifecycle — Operator Runbook

How FormicOS extracts, trusts, retrieves, evolves, and maintains knowledge.
Read this end-to-end before operating the knowledge system.

---

## 1. Extraction

When a colony completes successfully, the system automatically extracts
knowledge entries:

1. **LLM extraction** — An archivist pass distills the colony's output into
   typed entries: **skills** (reusable techniques) and **experiences**
   (observed outcomes with polarity).
2. **Transcript harvest** (hook position 4.5) — Before structured extraction,
   the system scans the raw colony transcript for bug root causes,
   conventions, and tool configurations. Deduplicates against existing
   entries at a 0.82 cosine threshold. Entries use a `:harvest` suffix
   for replay safety.
3. **Inline dedup** — Before emitting each entry, a cosine check (threshold
   0.92) detects near-duplicates. If a match exists, the system reinforces
   the existing entry's confidence instead of creating a duplicate.
4. **Security scan** — Each entry passes a 5-axis scan (prompt injection,
   data exfiltration, credential leakage, code safety, credential detection
   via detect-secrets). Credential scanning uses dual-config: prose-mode
   plugins exclude entropy-based detectors to reduce false positives.
   Findings with `scan_status="high"` result in `status="rejected"`.
   Credential values in tool outputs are redacted as `[REDACTED:type]`.
5. **Event emission** — A `MemoryEntryCreated` event is emitted per entry.
   The projection store indexes it; the memory store (Qdrant) persists the
   embedding for vector search.

Extraction is automatic. No operator action is required.

### Web foraging input path (Wave 44)

The Forager adds a second knowledge input channel: bounded web acquisition.
When retrieval exposes a gap (low-confidence results, coverage gaps, stale
clusters), the system can search the web, fetch pages, extract content, and
admit the results through the same lifecycle as colony-produced knowledge.

Key invariants:

- Forager-admitted entries reuse `MemoryEntryCreated` at `candidate` status.
  There is no separate "proposed knowledge" event type.
- Web-sourced entries start with conservative priors (low-to-moderate
  confidence) and never outrank colony-earned knowledge by default.
- All fetched content passes through the same 5-axis security scan and
  admission scoring pipeline as colony-extracted knowledge.
- Entries carry auditable forager provenance: `source_url`, `fetch_timestamp`,
  `fetch_level`, `forager_trigger`, `forager_query`, and `quality_score`.
- The existing lifecycle (candidate → active → verified, decay, Thompson
  Sampling retrieval, co-occurrence reinforcement, operator overlays) applies
  unchanged.

The Forager does not get a privileged admission path. It translates fetched
content into ordinary candidate entries, and usage decides whether those
entries earn trust.

---

## 2. Admission and Trust Levels

Each entry has a `scan_status`, an admission score, and a `status`.
Wave 38 added a real admission gate so knowledge is not accepted purely on
semantic relevance or source success.

### Admission scoring

New entries are evaluated across seven signals:

- confidence / posterior quality
- scanner findings
- provenance richness
- federation trust
- observation mass
- content type prior
- recency

Hard rejects occur on critical/high scanner findings or extremely weak
composite scores. Borderline entries are usually demoted rather than deleted,
so operators can still inspect what the system chose not to trust.

### Status and retrieval participation

Each entry also has a `status`:

| scan_status | Resulting status | Meaning |
|-------------|-----------------|---------|
| `high` or `critical` | `rejected` | Security concern — entry is excluded from retrieval |
| `safe`, `low`, or `medium` | `candidate` | Awaiting validation |
| *(source colony succeeded)* | `verified` | Promoted automatically when the source colony completed successfully |

Only `verified`, `active`, and `candidate` entries participate in retrieval.
Rejected and stale entries are excluded. Weak federated entries are further
discounted at retrieval time so local verified knowledge remains dominant
under ordinary conditions.

---

## 3. Thread Scoping

Every entry carries a `thread_id` linking it to the workflow thread where it
was created.

- **Thread-scoped entries** receive a **thread_bonus of 1.0** (weighted at
  0.07 in the composite score) when the searching colony belongs to the same
  thread.
- **Workspace-wide entries** have no thread_id — they are available to all
  colonies in the workspace.

### Promoting entries

To promote a thread-scoped entry to workspace-wide, use the Knowledge
browser's "Promote" button or emit a `MemoryEntryScopeChanged` event. This
clears the entry's `thread_id`, making it globally available.

---

## 4. Retrieval — Thompson Sampling Composite Scoring

When a colony or agent searches knowledge, results are ranked by a 6-signal
composite score (ADR-044) that balances exploitation of proven knowledge
with exploration of uncertain entries.

### Formula

```
score = 0.38 * semantic
      + 0.25 * thompson
      + 0.15 * freshness
      + 0.10 * status_bonus
      + 0.07 * thread_bonus
      + 0.05 * cooccurrence
```

### Signal ranges

| Signal | Range | Source |
|--------|-------|--------|
| `semantic` | [0, 1] | Cosine similarity from Qdrant vector search |
| `thompson` | [0, 1] | Random sample from Beta(alpha, beta) — the entry's confidence posterior |
| `freshness` | [0, 1] | Exponential decay with 90-day half-life: `2^(-age_days/90)` |
| `status_bonus` | [0, 1] | verified=1.0, active=0.8, candidate=0.5, stale=0.0, unknown/missing=0.0 |
| `thread_bonus` | {0.0, 1.0} | 1.0 if entry's thread matches the searching colony's thread, 0.0 otherwise |
| `cooccurrence` | [0, 1] | Sigmoid-normalized max co-occurrence weight with other results: `1 - e^{-0.6w}` |

### Tiered retrieval

Results are returned at one of four detail tiers to minimize token usage:

| Tier | ~Tokens/result | Fields |
|------|---------------|--------|
| `summary` | ~15 | id, title, summary (100 chars), confidence_tier |
| `standard` | ~75 | + content_preview (200 chars), domains, decay_class |
| `full` | ~200+ | + full content, conf_alpha/beta, merged_from, co-occurrence cluster |
| `auto` | varies | Starts at summary; escalates if coverage is thin |

Auto-escalation logic: if ≥2 unique source colonies and top score >0.5 →
summary. If ≥1 source and score >0.35 → standard. Otherwise → full.

### Budget-aware context assembly

Colony context is assembled with per-scope token budgets:

| Scope | Budget % |
|-------|----------|
| task_knowledge | 35% |
| observations | 20% |
| structured_facts | 15% |
| round_history | 15% |
| scratch_memory | 15% |

### What this means for operators

- **High-confidence entries** (high alpha, low beta) produce Thompson samples
  near their posterior mean — they are *exploited* reliably.
- **Uncertain entries** (alpha ≈ beta, low total) produce high-variance
  Thompson samples — they are *explored* occasionally, getting a chance to
  prove themselves.
- **Low-confidence entries** (low alpha, high beta) produce low Thompson
  samples — they *fade* from retrieval naturally.
- **Co-accessed entries** that frequently appear together in successful
  colonies get a small but meaningful co-occurrence boost (~5%).

- **Pinned entries** receive a local retrieval boost on the current instance.
- **Muted or invalidated entries** are filtered out locally without mutating
  shared confidence truth.

> **Note:** All signals are normalized to [0, 1]. Weights sum to 1.0.

---

## 5. Confidence Evolution

Each entry carries a Beta distribution posterior: `Beta(alpha, beta)`.

### Prior

All entries start with `Beta(5.0, 5.0)`. This prior was deliberately chosen
(ADR-039) to match the legacy `DEFAULT_PRIOR_STRENGTH = 10.0`. It requires
approximately **10 observations** before data dominates the prior.

### Update cycle

1. Colony completes.
2. The system matches knowledge access traces (which entries were retrieved
   and used) to the colony outcome.
3. For each accessed entry, a `MemoryConfidenceUpdated` event is emitted:
   - Colony succeeded → `delta_alpha = clip(0.5 + quality_score, 0.5, 1.5)`
   - Colony failed → bounded `delta_beta` based on failure penalty
4. The projection store updates the entry's alpha/beta.
5. Future Thompson samples reflect the updated posterior.

Current repo state: the old flat `alpha += 1` / `beta += 1` rule has been
replaced by quality-weighted deltas. Successful colonies apply a clipped
alpha gain derived from `quality_score`, while failure paths apply a bounded
beta penalty.

### Important boundary: operator overlays are not confidence mutations

Pin, mute, invalidate, and annotation actions are replayable operator
overlays. They do not silently change `conf_alpha` or `conf_beta`, and they
do not emit `MemoryConfidenceUpdated` on their own. Shared epistemic truth
and local editorial authority are intentionally separate.

### Monitoring

If entries plateau at ~0.5 confidence after 20+ observations, the prior is
dominating. Consider:
- Using the confidence reset handler (see §8) to reset stuck entries.
- In a future wave, reducing the prior to `Beta(2, 2)`.

---

## 6. Maintenance Services

Three deterministic maintenance services run on a daily schedule and can be
triggered manually.

### Dedup consolidation

- **Auto-merge** (cosine similarity ≥ 0.98): Emits a `MemoryEntryMerged`
  event. Content strategy is `keep_longer` if the source content exceeds
  1.2x the target length, otherwise `keep_target`. Domains are unioned.
  The `merged_from` provenance chain accumulates all absorbed entry IDs.
- **LLM-confirmed** (similarity in [0.82, 0.98)): An LLM judges whether the
  pair is truly duplicate. Confirmed → `MemoryEntryMerged` with
  `content_strategy="llm_selected"`. Denied → pair is marked dismissed
  (durable, skipped on future runs).
- **Dismissed pairs** are tracked via `last_status_reason` and excluded from
  future dedup runs.

> **Wave 33 change:** Auto-merge and LLM-confirmed merges now emit
> `MemoryEntryMerged` instead of `MemoryEntryStatusChanged(new_status="rejected")`.
> This preserves full provenance and content selection history.

### Stale sweep

Entries not accessed in **90 days** (and not already rejected/stale) are
transitioned to `stale` status. Additionally, entries with
`prediction_error_count >= 5` and `access_count < 3` are swept as stale.

### Prediction error counters

When a search returns a semantically-weak top result (cosine < 0.38), the
entry's `prediction_error_count` is incremented and the query is recorded.
This is projection-only (lossy on replay). High prediction error counts
feed the stale sweep trigger above.

### Contradiction detection

Entries with:
- Opposite polarity (positive vs negative)
- Overlapping domains (Jaccard similarity > 0.3)

are flagged as contradictions. The Knowledge browser shows these for operator
resolution.

---

## 7. Archival Behavior

Current repo state: archival is a lifecycle transition, not a separate hidden
confidence mutation path. Long-term forgetting comes from query-time gamma
decay, stale sweep logic, and operator/editorial overlays. Promoted knowledge
remains workspace-visible after thread archival.

When a thread is archived, unpromoted thread-scoped entries undergo confidence
decay:

```
alpha *= 0.8
beta  *= 1.2
```

With hard floors: `alpha >= 1.0` and `beta >= 1.0`.

### Known tension

This formula is **asymmetric** — it reduces the success count while
increasing the failure count, actively biasing the posterior mean downward
rather than just widening uncertainty.

When gamma-decay ships in Wave 32, this formula must be redesigned. Three
options under consideration:

1. **Symmetric decay:** `alpha *= 0.9, beta *= 0.9` — widens uncertainty
   without directional bias.
2. **Lower-gamma variant for archived entries:** `gamma_archived=0.85` vs
   `gamma_active=0.98` — faster forgetting for archived context.
3. **Subsumption into gamma-decay with hard floor:** Archived entries use the
   same gamma-decay mechanism but with a lower gamma and enforce
   `alpha >= alpha_0, beta >= beta_0` after any decay.

---

## 8. How to Trigger Maintenance Manually

Use the Queen's `query_service` tool:

```
query_service(service_type="service:consolidation:dedup")
query_service(service_type="service:consolidation:stale_sweep")
query_service(service_type="service:consolidation:contradiction")
query_service(service_type="service:consolidation:confidence_reset")
```

The **confidence reset** handler resets entries that are stuck at mediocre
confidence: entries with 50+ observations beyond the prior and a posterior
mean between 0.35 and 0.65 are reset to `Beta(5.0, 5.0)`. This is
manual-only — it does not run on the daily schedule.

The Knowledge browser also exposes Dedup and Stale Sweep buttons directly.

---

## 9. How to Read Confidence

### Posterior mean

```
confidence = alpha / (alpha + beta)
```

A value of 0.72 means "72% of observations led to successful outcomes."

### Certainty (observation count)

The sum `alpha + beta` indicates how much data backs the estimate. Subtract
the prior (10.0) to get the effective observation count.

| alpha + beta | Effective observations | Interpretation |
|--------------|----------------------|----------------|
| 10 | 0 | Prior only — no data yet |
| 15 | 5 | Early — still uncertain |
| 30 | 20 | Moderate — data starting to dominate |
| 60 | 50 | Strong — posterior is tight |

### UI confidence bars

The Knowledge browser displays:
- **Confidence percentage** — the posterior mean as a percentage.
- **Bar width** — proportional to `min((alpha + beta) / 50, 1.0)`, showing
  certainty. A narrow bar means little data; a full-width bar means high
  certainty.

---

## 10. How to Promote Entries

Thread-scoped entries are visible only to colonies in the same thread. To
make an entry available workspace-wide:

1. **Knowledge browser:** Click the "Promote" button next to any
   thread-scoped entry.
2. **Programmatically:** The system emits a `MemoryEntryScopeChanged` event
   that clears the entry's `thread_id`.

After promotion, the entry loses its thread bonus (1.0 at weight 0.07) but
becomes available to all colonies in the workspace.

### When to promote

- The knowledge is generally useful beyond the current thread's scope.
- The thread is about to be archived and you want to preserve high-value
  entries.

### What NOT to promote

- Thread-specific context that would be misleading outside the original
  workflow.
- Low-confidence entries that haven't proven themselves yet.

---

## 11. Decay Classes

Each knowledge entry carries a `decay_class` that controls how fast its
confidence fades when not observed:

| Decay class | Gamma (γ) | Half-life | Use case |
|-------------|-----------|-----------|----------|
| `ephemeral` | 0.98 | ~34 days | Transient context, tool configs |
| `stable` | 0.995 | ~139 days | Core skills, patterns |
| `permanent` | 1.0 | ∞ | Architectural decisions, invariants |

Gamma-decay is applied at **query time** via the ObservationCRDT, not stored
in the entry. The formula: `effective_alpha = prior + Σ(γ^elapsed_days × count)`.

A hard cap of **MAX_ELAPSED_DAYS = 180** prevents gamma from collapsing
observations beyond recovery. For ephemeral entries at 180 days,
`0.98^180 ≈ 0.027` — observations retain ~2.7% weight, not zero.

Default decay class for new entries is `ephemeral`.

---

## 12. Co-occurrence

When a colony accesses multiple knowledge entries and succeeds, the system
reinforces co-occurrence weights between each pair of accessed entries.

- **Result-result reinforcement:** 1.05x weight multiplier on query co-access.
- **Decay:** Co-occurrence weights decay at γ=0.995 per day. Weights below
  0.1 are pruned.
- **Weight cap:** 10.0 (prevents runaway reinforcement).
- **Scoring:** Co-occurrence is a scoring signal (weight 0.05, ADR-044).
  Sigmoid normalization: `1 - e^{-0.6w}` maps raw weight to [0, 1].

Data lives in `ProjectionStore.cooccurrence_weights` as `CooccurrenceEntry`
dataclass instances keyed by canonical `(id_a, id_b)` tuples.

### Distillation candidates

Dense co-occurrence clusters (≥5 entries, avg weight >3.0) are identified
during the co-occurrence decay maintenance pass and stored in
`ProjectionStore.distillation_candidates`. Wave 35 will use these to
trigger archivist colonies that synthesize cluster knowledge.

### knowledge_feedback tool

Agents can provide explicit quality feedback on retrieved entries via the
`knowledge_feedback` tool (available to coder, reviewer, researcher castes):

- `helpful=true` → emits `MemoryConfidenceUpdated` with
  `reason="agent_feedback_positive"` (alpha increases).
- `helpful=false` → increments `prediction_error_count` and emits
  `MemoryConfidenceUpdated` with `reason="agent_feedback_negative"`
  (beta increases).

This closes the agent-to-knowledge feedback loop, allowing agents to
directly improve the knowledge system's accuracy.

---

## 13. Proactive Intelligence

The system generates deterministic intelligence briefings (no LLM calls)
from projection signals. The current rule set spans 14 actionable insights.

**Knowledge rules (7):**

| Rule | Category | Severity | Trigger | suggested_colony? |
|------|----------|----------|---------|------------------|
| 1. Confidence decline | `confidence` | attention | Alpha dropped >20% from peak in 7 days | No |
| 2. Contradiction | `contradiction` | action_required | Two verified entries with opposite polarity and >30% domain overlap | **Yes** (researcher) |
| 3. Federation trust drop | `federation` | attention | Peer trust score <0.5 | No |
| 4. Coverage gap | `coverage` | attention/info | 3+ entries in a domain with 3+ prediction errors | **Yes** (researcher) |
| 5. Stale cluster | `staleness` | attention | Co-occurrence cluster where all entries have >3 prediction errors | **Yes** (researcher) |
| 6. Merge opportunity | `merge` | info | Two entries with >50% domain overlap and >50% title similarity | No |
| 7. Federation inbound | `inbound` | info | Foreign entries in a domain with no local coverage | No |

**Performance rules (4):**

| Rule | Category | Severity | Trigger |
|------|----------|----------|---------|
| 8. Strategy efficiency | `performance` | info | Strategy averages >15% lower quality than best (≥3 colonies each) |
| 9. Diminishing rounds | `performance` | attention | ≥2 colonies ran 10+ rounds with <40% quality |
| 10. Cost outlier | `performance` | info | Colony cost >2.5x workspace median (≥5 colonies) |
| 11. Knowledge ROI | `performance` | attention | >30% of spend on successful colonies that extracted zero entries |

Performance rules analyze `ColonyOutcome` projections. All deterministic,
no LLM. The Queen references these as recommendations, not automatic tuning.

Current repo state: the briefing layer also includes adaptive evaporation,
branching-factor stagnation, and earned-autonomy recommendations on top of the
original 7 knowledge rules and 4 performance rules.

Rules 2, 4, 5 include `suggested_colony` — a structured colony configuration
for auto-dispatch. Briefings are injected into the Queen's system prompt
and exposed via `formicos://briefing/{workspace_id}` MCP resource and
`/api/v1/briefing/{workspace_id}` REST endpoint.

### Entry sub-types

Entries carry a granular `sub_type` within their category:

| Entry type | Sub-types |
|-----------|-----------|
| `skill` | `technique`, `pattern`, `anti_pattern` |
| `experience` | `decision`, `convention`, `learning`, `bug` |

Sub-types are classified during LLM extraction and transcript harvest.
The Knowledge browser shows sub-type badges. API and MCP resources
support `sub_type` filtering.

---

## 14. Federation

FormicOS instances can exchange knowledge via push/pull replication.

### ObservationCRDT

Each knowledge entry is backed by an `ObservationCRDT` (`core/crdt.py`):
- **G-Counters** for success/failure observation counts (per-instance, grow-only)
- **LWW Registers** for content, entry_type, and decay_class
- **G-Sets** for domain tags and archival markers

All CRDT components merge independently: counters use pairwise-max, LWW
registers use timestamp (with node_id tie-breaking), sets use union.
Gamma-decay is applied at query time, preserving monotonic CRDT invariants.

### Trust discounting

Current repo state: peer failures are asymmetric (they add `2.0` to beta),
foreign knowledge is discounted by `trust * 0.7^hop` with a `0.5` cap, and
retrieval applies an additional federated status penalty so weak foreign
candidate entries do not outrank strong local verified knowledge.

Trust between peers uses `PeerTrust` (`surface/trust.py`) — the 10th
percentile of a Beta posterior, not the mean. This penalizes uncertainty:
a new peer with little history scores low even if its mean is high.

- `PeerTrust(α, β).score` = 10th percentile of `Beta(α, β)`
- `PeerTrust(α, β).mean` = `α / (α + β)` (always ≥ score)
- Foreign knowledge is discounted by hop: `trust * 0.7^hop` with a `0.5` cap

### Conflict resolution

When contradictory entries arrive from different instances, resolution uses
three phases:

1. **Pareto dominance** — If one entry dominates on 2+ criteria (evidence,
   provenance, recency), it wins immediately.
2. **Adaptive threshold** — Composite score comparison with a threshold that
   widens when evidence is low (encouraging exploration).
3. **Competing** — If neither entry clearly wins, both are kept as competing
   hypotheses for the operator. Competing pairs are tracked in projection
   state (`ProjectionStore.competing_pairs`) and lazily rebuilt when memory
   entries change. At standard and full retrieval tiers, results are
   annotated with a `competing_with` field listing competitor IDs, titles,
   and confidence means.

### Replication

Federation uses CouchDB-style push/pull replication (`surface/federation.py`):
- **Push:** Local CRDT events are sent to peers, filtered by replication
  filter (domain allowlist, min confidence, entry types, thread exclusions).
- **Pull:** Remote events are received, cycle-prevented (skip own instance
  events), and applied to projections.
- **Feedback:** Validation results (success/failure) update peer trust.

### Events

Five events support federation (ADR-042):
- `CRDTCounterIncremented` — G-Counter increment
- `CRDTTimestampUpdated` — LWW observation timestamp
- `CRDTSetElementAdded` — G-Set element addition
- `CRDTRegisterAssigned` — LWW register assignment
- `MemoryEntryMerged` — Entry merge with provenance

---

## Appendix: Step Definitions and Knowledge

Defining workflow steps after colonies have already completed will **not**
retroactively bind completed colonies to steps. This is expected — steps are
Queen scaffolding for future work, not a retrospective classification tool.

---

## Appendix: Self-Maintenance Loop

Current repo state: `generate_briefing()` now covers knowledge health,
performance, evaporation, branching, and earned-autonomy rules. The
"7 rules" framing below only describes the original knowledge-health subset.

The self-maintenance loop connects proactive intelligence insights to
automatic colony dispatch:

1. **Insight generation** — `generate_briefing()` identifies issues via 7 rules
2. **SuggestedColony** — 3 rules (contradiction, coverage gap, stale cluster)
   include ready-to-dispatch colony configurations
3. **Policy check** — `MaintenanceDispatcher` evaluates the workspace's
   `MaintenancePolicy`:
   - `suggest`: no auto-dispatch (default)
   - `auto_notify`: dispatch only categories listed in `auto_actions`
   - `autonomous`: dispatch all eligible categories
4. **Budget + cap** — `daily_maintenance_budget` and `max_maintenance_colonies`
   prevent runaway spending
5. **Dispatch** — Colony spawns with `[maintenance:{category}]` task prefix
6. **Outcome** — Colony outcome feeds back into confidence updates

---

## Appendix: Knowledge Distillation Pipeline

Dense co-occurrence clusters are synthesized into higher-order entries:

1. **Cluster detection** — During co-occurrence decay maintenance, BFS finds
   connected components with edge weight > 2.0
2. **Density check** — Clusters with ≥5 entries and avg weight > 3.0 qualify
3. **Archivist synthesis** — When maintenance policy allows (`distillation`
   in `auto_actions`), an archivist colony synthesizes the cluster
4. **KnowledgeDistilled event** — Records `distilled_entry_id`,
   `source_entry_ids`, and `cluster_avg_weight`
5. **Elevated entry** — Distilled entry gets `decay_class="stable"` and
   elevated alpha (capped at 30)

---

## Appendix: Mastery-Restoration Bonus

When a knowledge entry's confidence has decayed significantly but was
historically strong:

- **Trigger**: `current_alpha < peak_alpha * 0.5` AND `decay_class` is
  `stable` or `permanent`
- **Bonus**: `gap * 0.2` where `gap = peak_alpha - current_alpha`
- **Effect**: Successful re-observations restore confidence faster than
  cold-start entries, reflecting that re-learned knowledge is more reliable
- **Tracking**: `peak_alpha` stored in projections via
  `MemoryConfidenceUpdated` handler

---

## Appendix: Per-Workspace Weight Tuning

Composite retrieval weights can be tuned per workspace:

- **Tool**: `configure_scoring` MCP tool sets custom weights
- **Storage**: Persisted via `WorkspaceConfigChanged` event
- **Fallback**: Missing workspaces use global defaults (ADR-044)
- **Invariants**: All 6 signals must be present; weights must sum to 1.0
- **Impact**: Setting `cooccurrence=0.0` disables co-occurrence boost;
  higher `semantic` weight prioritizes embedding similarity over exploration

---

## Appendix: Colony Outcome Feedback Loop

Current repo state: outcome history now also feeds escalation reporting and
configuration recommendation surfaces, not just the four original
performance rules.

Colony outcomes close the loop between execution and knowledge intelligence:

1. **Outcome derivation** — `ColonyOutcome` is computed silently from
   existing events during replay (no new event types, ADR-047):
   - `ColonySpawned` → workspace, thread, strategy, caste_composition
   - `RoundCompleted` → total_rounds, total_cost
   - `ColonyCompleted` / `ColonyFailed` / `ColonyKilled` → succeeded, duration
   - `MemoryEntryCreated` → entries_extracted
   - `KnowledgeAccessRecorded` → entries_accessed

2. **Performance rules** — Four deterministic rules analyze accumulated
   outcomes per workspace (no LLM):
   - Strategy efficiency (compare quality across strategies)
   - Diminishing rounds (flag long-running low-quality colonies)
   - Cost outlier (flag colonies costing >2.5x median)
   - Knowledge ROI (flag spend without knowledge extraction)

3. **Queen briefing** — Performance insights appear in the proactive
   briefing alongside knowledge insights. The Queen references these
   as recommendations, not automatic overrides.

4. **REST surface** — `GET /api/v1/workspaces/{id}/outcomes?period=7d`
   returns aggregate outcome metrics.

Outcomes are replay-derived — the event log is the sole source of truth.
`ColonyOutcome` is rebuilt during replay and stored in projection memory.
No outcome editing, no separate persistence.

---

## Appendix: Forager Replay Surface (Wave 44)

The Forager added exactly 4 event types to the closed union in Wave 44 (58 → 62):

| Event | Purpose | Replay role |
|-------|---------|-------------|
| `ForageRequested` | System decided to forage | When/why a cycle started |
| `ForageCycleCompleted` | Summary of cycle results | What the cycle accomplished |
| `DomainStrategyUpdated` | Learned fetch-level preference | Durable domain strategy |
| `ForagerDomainOverride` | Operator domain trust action | Operator co-authorship |

### What stays log-only in v1

Individual search requests, fetch attempts, and content rejections are audit
details. They are structured-logged but do not become first-class replay
events. This keeps the event surface minimal and justified.

### Projection state

- **Domain strategies** — per-workspace, per-domain preferred fetch level,
  success/failure counts. Survives replay.
- **Forage cycle summaries** — per-workspace list of completed cycles with
  mode, reason, counts, and duration. Links back to the originating request.
- **Domain overrides** — per-workspace, per-domain operator trust/distrust
  actions. `reset` removes the override entirely.

### Forager trigger modes

| Mode | Trigger | Description | Status |
|------|---------|-------------|--------|
| `reactive` | Low-confidence live-task retrieval | Highest-value; gap detected during colony work | Operational |
| `proactive` | Briefing rule (stale cluster, coverage gap, etc.) | Background; lower priority than reactive | Operational |
| `operator` | Manual operator request | Direct operator control | Operational |

> **Current state:** Proactive foraging runs through the scheduled maintenance
> loop. `proactive_intelligence` emits bounded `forage_signal` metadata,
> `MaintenanceDispatcher` evaluates workspace briefings, and eligible signals
> are handed to `ForagerService` for background execution. Reactive,
> proactive, and operator-triggered foraging are operational.
