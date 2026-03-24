# Wave 33 Track C — Computational CRDTs + Federation

## Role

You are a coder building the federation foundation: CRDT primitives, the ObservationCRDT composite type, 5 new event types (4 CRDT + 1 MemoryEntryMerged), vector clocks, Bayesian trust, conflict resolution, the federation protocol, provenance schemas, and the canonical transcript view. This is the largest track in Wave 33.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/042-event-union-expansion.md` (approved) BEFORE writing events. Follow the exact schemas in D1 and D2.
- Read `docs/decisions/041-knowledge-tuning.md` — you must understand gamma-decay and Beta posteriors for the CRDT query-time computation.
- Read `docs/decisions/043-cooccurrence-data-model.md` — you do NOT implement co-occurrence, but you need to know it exists to avoid overlap.
- Read `docs/contracts/events.py` — understand the event union structure, the manifest self-check, and the `__all__` exports. You are modifying this file.

## File ownership

You OWN these files:

| File | Status | Changes |
|------|--------|---------|
| `core/crdt.py` | CREATE | ~300 LOC: GCounter, LWWRegister, GSet, ObservationCRDT |
| `core/vector_clock.py` | CREATE | ~80 LOC: VectorClock |
| `core/types.py` | MODIFY | ProvenanceChain, KnowledgeExchangeEntry, ReplicationFilter, ValidationFeedback, Resolution enum |
| `core/events.py` | MODIFY | 5 new event types + union expansion + manifest update |
| `docs/contracts/events.py` | MODIFY | Mirror of core/events.py for contract documentation |
| `surface/trust.py` | CREATE | ~150 LOC: PeerTrust, trust scoring, discount |
| `surface/conflict_resolution.py` | CREATE | ~200 LOC: Pareto + adaptive threshold |
| `surface/federation.py` | CREATE | ~400 LOC: peer manager, push/pull, validation feedback |
| `surface/transcript_view.py` | CREATE | ~200 LOC: ColonyTranscriptView + adapters |
| `surface/projections.py` | MODIFY | CRDT state projection handlers, ObservationCRDT rebuild |
| `surface/maintenance.py` | MODIFY | Dedup handler → emit MemoryEntryMerged |
| `adapters/federation_transport.py` | CREATE | ~100 LOC: A2A DataPart transport |
| `docs/schemas/formicos-prov-context.jsonld` | CREATE | Static JSON-LD context file |
| `tests/unit/core/test_crdt.py` | CREATE | CRDT primitive + ObservationCRDT tests |
| `tests/unit/core/test_vector_clock.py` | CREATE | Vector clock tests |
| `tests/unit/surface/test_trust.py` | CREATE | PeerTrust tests |
| `tests/unit/surface/test_conflict_resolution.py` | CREATE | Conflict resolution tests |
| `tests/unit/surface/test_federation.py` | CREATE | Federation round-trip tests |
| `tests/unit/surface/test_memory_entry_merged.py` | CREATE | Merge event + dedup handler modification tests |

## DO NOT TOUCH

- `surface/colony_manager.py` — Track A owns
- `surface/memory_extractor.py` — Track A owns
- `surface/knowledge_catalog.py` — Track A owns
- `surface/knowledge_constants.py` — Track A owns
- `surface/queen_thread.py` — Track A owns
- `surface/credential_scan.py` — Track B owns
- `surface/memory_scanner.py` — Track B owns
- `surface/structured_error.py` — Track B owns
- `surface/mcp_server.py` — Track B owns
- `surface/event_translator.py` — Track B owns
- `surface/routes/*` — Track B owns
- `surface/ws_handler.py` — Track B owns
- `surface/commands.py` — Track B owns
- `surface/agui_endpoint.py` — Track B owns

## Overlap rules

- `core/types.py`: You add ProvenanceChain, KnowledgeExchangeEntry, etc. Track A adds DecayClass + decay_class on MemoryEntry. Different classes — no conflict. Be aware that Track A adds `DecayClass` StrEnum — you will reference it in ObservationCRDT's decay_class LWWRegister.
- `surface/maintenance.py`: You modify `_handle_dedup()` (line 25) to emit `MemoryEntryMerged` instead of `MemoryEntryStatusChanged` at lines 58 and 143. **This is the riskiest overlap** — you are changing existing code, not adding new functions. Track A adds `make_cooccurrence_decay_handler()` (new function) + prediction error criteria to `_handle_stale()` (line 204, new logic in existing function). Track B adds `make_credential_sweep_handler()` (new function). All touch different functions, but verify after integration that imports and function signatures are consistent.
- `surface/projections.py`: You add CRDT state handlers + `_on_memory_entry_merged()` handler registered in the dispatch dict. Track A adds CooccurrenceEntry + harvest tracking. Different projection fields and handlers.

## Internal sequencing

C1 (CRDT primitives) + C3 (CRDT events) + C4 (merge event) + C5 (vector clocks) have NO dependencies — implement first.
C2 (ObservationCRDT) depends on C1.
C6 (trust) + C7 (conflict) + C8 (federation) depend on C1, C2, C5.
C9 (schemas + transcript view) is independent.

---

## C1. CRDT primitives (~300 LOC)

### Where

Create `core/crdt.py`. This is in the core layer — MUST NOT import from engine, adapters, or surface.

### Implementation

```python
"""Conflict-free Replicated Data Types for federated knowledge.

Three primitives: GCounter (grow-only counter), LWWRegister (last-writer-wins),
GSet (grow-only set). Merge operations are commutative, associative, idempotent.

Design references: Shapiro et al. 2011 (CRDTs comprehensive study),
python3-crdt and ericmoritz/crdt (patterns only, not dependencies).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GCounter:
    """Grow-only counter. Per-node integer values. Merge = pairwise max.

    Integer-only by design: observation counts must be exact.
    The prior (5.0) and decay are applied at query time, not stored here.
    """
    counts: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str, delta: int = 1) -> None:
        if delta < 1:
            raise ValueError("G-Counter delta must be positive")
        self.counts[node_id] = self.counts.get(node_id, 0) + delta

    def merge(self, other: GCounter) -> GCounter:
        """Pairwise max. Commutative, associative, idempotent."""
        all_keys = set(self.counts) | set(other.counts)
        return GCounter(counts={
            k: max(self.counts.get(k, 0), other.counts.get(k, 0))
            for k in all_keys
        })

    def value(self) -> int:
        """Total count across all nodes."""
        return sum(self.counts.values())


@dataclass
class LWWRegister:
    """Last-Writer-Wins Register. Higher timestamp wins. Ties broken by node_id."""
    value: Any = None
    timestamp: float = 0.0
    node_id: str = ""

    def assign(self, value: Any, timestamp: float, node_id: str) -> None:
        if timestamp > self.timestamp or (timestamp == self.timestamp and node_id > self.node_id):
            self.value = value
            self.timestamp = timestamp
            self.node_id = node_id

    def merge(self, other: LWWRegister) -> LWWRegister:
        """Higher timestamp wins. Ties broken by node_id (lexicographic)."""
        if other.timestamp > self.timestamp or (
            other.timestamp == self.timestamp and other.node_id > self.node_id
        ):
            return LWWRegister(value=other.value, timestamp=other.timestamp, node_id=other.node_id)
        return LWWRegister(value=self.value, timestamp=self.timestamp, node_id=self.node_id)


@dataclass
class GSet:
    """Grow-only set. Merge = union. Elements never removed."""
    elements: set[str] = field(default_factory=set)

    def add(self, element: str) -> None:
        self.elements.add(element)

    def merge(self, other: GSet) -> GSet:
        return GSet(elements=self.elements | other.elements)

    def __contains__(self, element: str) -> bool:
        return element in self.elements
```

### Tests (property-based)

- GCounter: merge is commutative (`a.merge(b) == b.merge(a)`)
- GCounter: merge is associative (`a.merge(b).merge(c) == a.merge(b.merge(c))`)
- GCounter: merge is idempotent (`a.merge(a) == a`)
- GCounter: value is sum of all node counts
- GCounter: delta must be >= 1
- LWWRegister: higher timestamp wins
- LWWRegister: tie-breaking by node_id (lexicographic)
- GSet: merge is union
- GSet: elements never removed

---

## C2. ObservationCRDT composite type

### Where

Add to `core/crdt.py` after the primitives.

### Implementation

```python
@dataclass
class ObservationCRDT:
    """Computational CRDT for federated Bayesian confidence.

    Stores raw observation counts (G-Counters) and timestamps (LWW Registers).
    Gamma-decay is applied at query time, not stored in the CRDT.
    This separation ensures monotonic CRDT operations while preserving
    time-dependent confidence computation.

    Reference: Navalho, Duarte, Preguica (PaPoC 2015) —
    separate monotonic facts from derived computation.
    """
    successes: GCounter = field(default_factory=GCounter)
    failures: GCounter = field(default_factory=GCounter)
    last_obs_ts: dict[str, LWWRegister] = field(default_factory=dict)
    archived_by: GSet = field(default_factory=GSet)
    content: LWWRegister = field(default_factory=LWWRegister)
    entry_type: LWWRegister = field(default_factory=LWWRegister)
    domains: GSet = field(default_factory=GSet)
    decay_class: LWWRegister = field(default_factory=LWWRegister)

    def merge(self, other: ObservationCRDT) -> ObservationCRDT:
        """All components merge independently using their own semantics."""
        merged_ts = dict(self.last_obs_ts)
        for k, v in other.last_obs_ts.items():
            if k in merged_ts:
                merged_ts[k] = merged_ts[k].merge(v)
            else:
                merged_ts[k] = v
        return ObservationCRDT(
            successes=self.successes.merge(other.successes),
            failures=self.failures.merge(other.failures),
            last_obs_ts=merged_ts,
            archived_by=self.archived_by.merge(other.archived_by),
            content=self.content.merge(other.content),
            entry_type=self.entry_type.merge(other.entry_type),
            domains=self.domains.merge(other.domains),
            decay_class=self.decay_class.merge(other.decay_class),
        )

    def query_alpha(self, now: float, gamma_rates: dict[str, float], prior_alpha: float, max_elapsed_days: float = 180.0) -> float:
        """Compute effective alpha at query time with per-instance decay.

        Args:
            now: Current epoch seconds.
            gamma_rates: Mapping from decay_class name to gamma rate.
                         Callers pass GAMMA_RATES from knowledge_constants.
            prior_alpha: Prior alpha value (callers pass PRIOR_ALPHA).
            max_elapsed_days: Cap on elapsed days (ADR-041 hardening).
        """
        dc = self.decay_class.value if self.decay_class.value else "ephemeral"
        gamma = gamma_rates.get(dc, 0.98)
        alpha = prior_alpha
        for inst_id, count in self.successes.counts.items():
            ts_reg = self.last_obs_ts.get(inst_id)
            ts = ts_reg.timestamp if ts_reg else now
            elapsed = min((now - ts) / 86400.0, max_elapsed_days)
            alpha += (gamma ** max(elapsed, 0.0)) * count
        return max(alpha, 1.0)

    def query_beta(self, now: float, gamma_rates: dict[str, float], prior_beta: float, max_elapsed_days: float = 180.0) -> float:
        """Compute effective beta at query time with per-instance decay."""
        dc = self.decay_class.value if self.decay_class.value else "ephemeral"
        gamma = gamma_rates.get(dc, 0.98)
        beta = prior_beta
        for inst_id, count in self.failures.counts.items():
            ts_reg = self.last_obs_ts.get(inst_id)
            ts = ts_reg.timestamp if ts_reg else now
            elapsed = min((now - ts) / 86400.0, max_elapsed_days)
            beta += (gamma ** max(elapsed, 0.0)) * count
        return max(beta, 1.0)

    def query_confidence(self, now: float, gamma_rates: dict[str, float], prior_alpha: float, prior_beta: float, **kwargs: Any) -> float:
        """Posterior mean: alpha / (alpha + beta)."""
        a = self.query_alpha(now, gamma_rates=gamma_rates, prior_alpha=prior_alpha, **kwargs)
        b = self.query_beta(now, gamma_rates=gamma_rates, prior_beta=prior_beta, **kwargs)
        return a / (a + b)
```

**IMPORTANT: Layer violation.** `query_alpha()` must NOT import from `surface.knowledge_constants` — that's a core→surface import. Use **required parameters only** (no lazy imports, no default None with hidden imports):

```python
def query_alpha(self, now: float, gamma_rates: dict[str, float], prior_alpha: float, max_elapsed_days: float = 180.0) -> float:
```

All callers live in surface layer and pass `GAMMA_RATES`, `PRIOR_ALPHA` from `knowledge_constants.py`. The parameters are mandatory (no defaults that would need a fallback import). This keeps core layer pure with zero surface dependencies.

Track A is adding `GAMMA_RATES` and `PRIOR_ALPHA`/`PRIOR_BETA` to `surface/knowledge_constants.py`. Import those in your surface-layer callers (trust.py, federation.py, projections.py) and pass them to `query_alpha()`/`query_beta()`.

### Tests

- Two ObservationCRDTs with different counts → merge → query_alpha correct
- decay_class="permanent" → gamma=1.0, no decay, alpha = prior + sum(counts)
- decay_class="ephemeral" → gamma=0.98, alpha decays with elapsed time
- Archival: instance in archived_by → its observations decay from archive timestamp
- Merge is commutative and idempotent

---

## C3. CRDT event types (4 new events)

### Where

`core/events.py` — add after the Wave 30 events section (after line 836).

### Implementation

Follow the EXACT schemas from ADR-042 D1. Add all 4 event classes:

1. `CRDTCounterIncremented` — G-Counter increment
2. `CRDTTimestampUpdated` — LWW timestamp update
3. `CRDTSetElementAdded` — G-Set element addition
4. `CRDTRegisterAssigned` — LWW Register assignment

After adding the classes, update ALL FOUR maintenance points:

1. **FormicOSEvent union** (line 838-890): Add all 4 + MemoryEntryMerged to the Union
2. **EVENT_TYPE_NAMES manifest** (line 896-945): Add all 5 names
3. **_union_members frozenset** (line 948-967): Add all 5 classes
4. **__all__ exports** (line 997-1056): Add all 5 class names

The import-time self-check (lines 970-977) will catch any drift. Run `python -c "from formicos.core.events import *"` to verify.

### Also update `docs/contracts/events.py`

Mirror the changes. Update the docstring at the top:
```python
"""...
Wave 33: +5 events (CRDTCounterIncremented, CRDTTimestampUpdated,
CRDTSetElementAdded, CRDTRegisterAssigned, MemoryEntryMerged).
Union: 48 -> 53.
"""
```

### Tests

- Each event type serializes and deserializes correctly
- EVENT_TYPE_NAMES manifest matches union members (import-time check)
- All 53 types in the union

---

## C4. MemoryEntryMerged event

### Where

`core/events.py` — add alongside the CRDT events.

### Implementation

Follow the EXACT schema from ADR-042 D2:

```python
class MemoryEntryMerged(EventEnvelope):
    """Two knowledge entries merged, with full provenance trail."""
    model_config = FrozenConfig
    type: Literal["MemoryEntryMerged"] = "MemoryEntryMerged"
    target_id: str = Field(..., description="Surviving entry.")
    source_id: str = Field(..., description="Absorbed entry. Will be marked rejected.")
    merged_content: str = Field(..., description="Content that survived selection.")
    merged_domains: list[str] = Field(..., description="Union of both entries' domains.")
    merged_from: list[str] = Field(..., description="Accumulated provenance chain.")
    content_strategy: Literal["keep_longer", "keep_target", "llm_selected"] = Field(...)
    similarity: float = Field(..., ge=0.0, le=1.0)
    merge_source: Literal["dedup", "federation"] = Field(...)
    workspace_id: str = Field(...)
```

### Dedup handler modification

In `surface/maintenance.py`, modify `_handle_dedup()` (line 25):

**Auto-merge (cosine >= 0.98)** at line 58: Replace `MemoryEntryStatusChanged(new_status="rejected")` with:
```python
# Determine content strategy
target_content = target_entry.get("content", "")
source_content = source_entry.get("content", "")
if len(source_content) > len(target_content) * 1.2:
    merged_content = source_content
    strategy = "keep_longer"
else:
    merged_content = target_content
    strategy = "keep_target"

# Union domains
target_domains = target_entry.get("domains", [])
source_domains = source_entry.get("domains", [])
merged_domains = list(set(target_domains) | set(source_domains))

# Build provenance chain
existing_merged_from = target_entry.get("merged_from", [])
merged_from = existing_merged_from + [source_id]

await runtime.emit_and_broadcast(MemoryEntryMerged(
    seq=0,
    type="MemoryEntryMerged",
    timestamp=datetime.utcnow(),
    address=f"{workspace_id}",
    target_id=target_id,
    source_id=source_id,
    merged_content=merged_content,
    merged_domains=merged_domains,
    merged_from=merged_from,
    content_strategy=strategy,
    similarity=similarity,
    merge_source="dedup",
    workspace_id=workspace_id,
))
```

**LLM-confirmed merge (cosine 0.82-0.98)** at line 143: Same replacement. For LLM-confirmed merges, `content_strategy="llm_selected"` and `merged_content` comes from the LLM's selection.

### Projection handler

In `surface/projections.py`, add `_on_memory_entry_merged()`:
```python
def _on_memory_entry_merged(store: ProjectionStore, event: FormicOSEvent) -> None:
    assert isinstance(event, MemoryEntryMerged)
    target = store.memory_entries.get(event.target_id)
    if target:
        target["content"] = event.merged_content
        target["domains"] = event.merged_domains
        target["merged_from"] = event.merged_from
        target["merge_count"] = target.get("merge_count", 0) + 1
    source = store.memory_entries.get(event.source_id)
    if source:
        source["status"] = "rejected"
        source["rejection_reason"] = f"merged_into:{event.target_id}"
```

Register in the handler dispatch dict alongside the other handlers.

### Tests

- Auto-merge (>= 0.98): emits MemoryEntryMerged, NOT MemoryEntryStatusChanged
- Content strategy: source content 1.5x target → keep_longer, source wins
- Content strategy: source content 0.8x target → keep_target, target wins
- Domains unioned: target has [A, B], source has [B, C] → merged has [A, B, C]
- merged_from accumulates: target already has [X], source is Y → merged_from = [X, Y]
- Projection: target updated, source rejected with reason

---

## C5. Vector clocks (~80 LOC)

### Where

Create `core/vector_clock.py`. Core layer — no surface/engine imports.

### Implementation

```python
"""Vector clocks for causal ordering in federated FormicOS instances.

At 2-10 instances: 160-240 bytes per clock, nanosecond comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VectorClock:
    clock: dict[str, int] = field(default_factory=dict)

    def increment(self, instance_id: str) -> VectorClock:
        new_clock = dict(self.clock)
        new_clock[instance_id] = new_clock.get(instance_id, 0) + 1
        return VectorClock(clock=new_clock)

    def merge(self, other: VectorClock) -> VectorClock:
        all_keys = set(self.clock) | set(other.clock)
        return VectorClock(clock={
            k: max(self.clock.get(k, 0), other.clock.get(k, 0))
            for k in all_keys
        })

    def happens_before(self, other: VectorClock) -> bool:
        """True if self strictly happens-before other."""
        all_keys = set(self.clock) | set(other.clock)
        at_least_one_less = False
        for k in all_keys:
            s = self.clock.get(k, 0)
            o = other.clock.get(k, 0)
            if s > o:
                return False
            if s < o:
                at_least_one_less = True
        return at_least_one_less

    def is_concurrent(self, other: VectorClock) -> bool:
        """True if neither happens-before the other."""
        return not self.happens_before(other) and not other.happens_before(self)
```

### Tests

- happens_before: {A:1} < {A:2} is True
- happens_before: {A:2} < {A:1} is False
- is_concurrent: {A:1, B:0} vs {A:0, B:1} is True
- merge: pairwise max
- increment: only increments the specified instance

---

## C6. Bayesian trust with conservative estimator (~150 LOC)

### Where

Create `surface/trust.py`.

### Implementation

```python
"""Bayesian trust scoring for federation peers.

Uses 10th percentile of Beta posterior instead of mean.
Research finding: mean-based trust lets a new peer reach 0.9 after
only 9 successes. 10th percentile requires ~30+ for 0.8.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class PeerTrust:
    alpha: float = 1.0  # successes + 1
    beta: float = 1.0   # failures + 1

    @property
    def score(self) -> float:
        """10th percentile of Beta posterior. Penalizes uncertainty.

        Uses the incomplete beta function approximation.
        scipy.stats.beta.ppf(0.10, alpha, beta) is the reference,
        but we use a pure-Python approximation to avoid the scipy dependency.
        """
        return _beta_ppf_approx(0.10, self.alpha, self.beta)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def record_success(self) -> None:
        self.alpha += 1.0

    def record_failure(self) -> None:
        self.beta += 1.0

    def decay(self, days: float, gamma: float = 0.9995) -> None:
        """Trust decay: retains 91.4% at 90 days, 83.5% at 180 days."""
        factor = gamma ** days
        # Decay toward the prior (1, 1) = uniform
        self.alpha = max(factor * self.alpha + (1 - factor) * 1.0, 1.0)
        self.beta = max(factor * self.beta + (1 - factor) * 1.0, 1.0)


def trust_discount(trust_score: float, hop: int = 0) -> float:
    """Discount factor for foreign knowledge observations.

    Applied at query time in ObservationCRDT, not stored in CRDT state.
    """
    return trust_score * (0.9 ** hop)


def _beta_ppf_approx(p: float, alpha: float, beta: float) -> float:
    """Approximate inverse CDF of Beta distribution.

    Uses the normal approximation for Beta when alpha+beta > 4,
    falls back to a simple quantile estimate otherwise.
    """
    if alpha <= 0 or beta <= 0:
        return 0.0
    n = alpha + beta
    if n > 4:
        # Normal approximation: Beta ~ N(mu, sigma^2)
        mu = alpha / n
        sigma = math.sqrt(alpha * beta / (n * n * (n + 1)))
        # Inverse normal CDF approximation (Abramowitz and Stegun)
        z = _inv_normal_approx(p)
        return max(0.0, min(1.0, mu + z * sigma))
    # Fallback: simple linear interpolation
    return max(0.0, alpha / n - 0.1)


def _inv_normal_approx(p: float) -> float:
    """Rational approximation of inverse normal CDF (Abramowitz & Stegun 26.2.23)."""
    if p <= 0.0:
        return -4.0
    if p >= 1.0:
        return 4.0
    if p > 0.5:
        return -_inv_normal_approx(1.0 - p)
    t = math.sqrt(-2.0 * math.log(p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return -(t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t))
```

**No scipy dependency.** The pure-Python approximation is sufficient for trust scoring (we need ~2 decimal places, not scientific precision). If scipy is available, use it; otherwise fall back to the approximation.

### Tests

- PeerTrust(1, 1).score → ~0.0 (new peer, no history)
- PeerTrust(11, 1).score → ~0.79 (10 successes)
- PeerTrust(31, 1).score → ~0.89 (30 successes)
- PeerTrust(10, 1).mean → ~0.909 (mean is higher than 10th percentile — that's the point)
- trust_discount(0.8, hop=0) → 0.8
- trust_discount(0.8, hop=1) → 0.72
- Decay at 90 days → retains ~91% of evidence

---

## C7. Conflict resolution with Pareto dominance + adaptive threshold (~200 LOC)

### Where

Create `surface/conflict_resolution.py`.

### Implementation

```python
"""Conflict resolution for contradictory knowledge entries.

Three-phase resolution:
1. Pareto dominance (obvious winner on 2+ criteria)
2. Composite score with adaptive threshold
3. Keep both as competing hypotheses
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Resolution(StrEnum):
    winner = "winner"        # one entry clearly dominates
    competing = "competing"  # both kept, higher-scoring is primary


@dataclass
class ConflictResult:
    resolution: Resolution
    primary_id: str
    secondary_id: str | None = None
    primary_score: float = 0.0
    secondary_score: float = 0.0
    method: str = ""  # "pareto", "threshold", "competing"


def resolve_conflict(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
) -> ConflictResult:
    """Resolve conflict between two contradictory entries."""

    # Phase 1: Pareto dominance
    # Criteria: evidence (total observations), recency, provenance length
    ev_a = entry_a.get("conf_alpha", 5) + entry_a.get("conf_beta", 5) - 10  # total evidence above prior
    ev_b = entry_b.get("conf_alpha", 5) + entry_b.get("conf_beta", 5) - 10
    rec_a = _recency_score(entry_a)
    rec_b = _recency_score(entry_b)
    prov_a = len(entry_a.get("merged_from", []))
    prov_b = len(entry_b.get("merged_from", []))

    a_dominates = 0
    b_dominates = 0
    margin = 1.5  # substantial margin for Pareto

    if ev_a > ev_b * margin: a_dominates += 1
    elif ev_b > ev_a * margin: b_dominates += 1
    if rec_a > rec_b * margin: a_dominates += 1
    elif rec_b > rec_a * margin: b_dominates += 1
    if prov_a > prov_b * margin: a_dominates += 1
    elif prov_b > prov_a * margin: b_dominates += 1

    id_a = entry_a.get("id", "")
    id_b = entry_b.get("id", "")

    if a_dominates >= 2:
        return ConflictResult(Resolution.winner, id_a, id_b, method="pareto")
    if b_dominates >= 2:
        return ConflictResult(Resolution.winner, id_b, id_a, method="pareto")

    # Phase 2: Composite score with adaptive threshold
    score_a = 0.6 * _normalize(ev_a) + 0.2 * rec_a + 0.2 * _normalize(prov_a)
    score_b = 0.6 * _normalize(ev_b) + 0.2 * rec_b + 0.2 * _normalize(prov_b)

    avg_evidence = (max(ev_a, 1) + max(ev_b, 1)) / 2
    threshold = 0.05 + 2.0 / avg_evidence

    if abs(score_a - score_b) > threshold:
        winner = id_a if score_a > score_b else id_b
        loser = id_b if score_a > score_b else id_a
        return ConflictResult(Resolution.winner, winner, loser,
                              primary_score=max(score_a, score_b),
                              secondary_score=min(score_a, score_b),
                              method="threshold")

    # Phase 3: Keep both as competing hypotheses
    primary = id_a if score_a >= score_b else id_b
    secondary = id_b if score_a >= score_b else id_a
    return ConflictResult(Resolution.competing, primary, secondary,
                          primary_score=max(score_a, score_b),
                          secondary_score=min(score_a, score_b),
                          method="competing")
```

### Tests

- Entry with 90 evidence + 180 days vs entry with 6 evidence + 1 day → Pareto dominance (evidence + provenance)
- Two entries with equal evidence → adaptive threshold applies
- Both entries uncertain (low evidence) → wide threshold → competing hypotheses
- Both entries strong (high evidence) → narrow threshold → clear winner

---

## C8. Federation protocol + selective replication (~400 LOC)

### Where

Create `surface/federation.py` and `adapters/federation_transport.py`.

### Implementation

**`surface/federation.py`** — peer management and replication logic:

```python
"""Federation protocol: CouchDB-style push/pull replication between FormicOS instances."""

@dataclass
class PeerConnection:
    instance_id: str
    endpoint: str
    trust: PeerTrust
    replication_filter: ReplicationFilter
    last_sync_clock: VectorClock

class FederationManager:
    def __init__(self, instance_id: str, projections: ProjectionStore, transport: FederationTransport):
        self._instance_id = instance_id
        self._projections = projections
        self._transport = transport
        self._peers: dict[str, PeerConnection] = {}
        self._clock = VectorClock()

    async def push_to_peer(self, peer_id: str) -> int:
        """Push local CRDT events since peer's last_sync_clock."""
        peer = self._peers[peer_id]
        events = self._get_events_since(peer.last_sync_clock)
        filtered = self._apply_replication_filter(events, peer.replication_filter)
        if not filtered:
            return 0
        await self._transport.send_events(peer.endpoint, filtered)
        peer.last_sync_clock = self._clock
        return len(filtered)

    async def pull_from_peer(self, peer_id: str) -> int:
        """Pull foreign CRDT events from peer."""
        peer = self._peers[peer_id]
        events = await self._transport.receive_events(peer.endpoint, since=peer.last_sync_clock)
        applied = 0
        for event in events:
            if event.instance_id == self._instance_id:
                continue  # Cycle prevention
            self._apply_foreign_event(event)
            applied += 1
        return applied

    async def send_validation_feedback(self, peer_id: str, entry_id: str, success: bool) -> None:
        """Report outcome of using foreign knowledge to the originating peer."""
        peer = self._peers[peer_id]
        if success:
            peer.trust.record_success()
        else:
            peer.trust.record_failure()
        await self._transport.send_feedback(peer.endpoint, entry_id, success)
```

**`adapters/federation_transport.py`** — transport layer:

```python
"""Federation transport via A2A DataPart (adapter layer)."""

class FederationTransport:
    """Abstract transport for federation events."""

    async def send_events(self, endpoint: str, events: list[dict]) -> None: ...
    async def receive_events(self, endpoint: str, since: VectorClock) -> list[dict]: ...
    async def send_feedback(self, endpoint: str, entry_id: str, success: bool) -> None: ...

class A2ADataPartTransport(FederationTransport):
    """Concrete transport using A2A DataPart protocol."""
    # Implementation using httpx to POST serialized CRDT events
    # to peer's A2A endpoint as DataPart artifacts
    ...
```

**ReplicationFilter** in `core/types.py`:
```python
class ReplicationFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    domain_allowlist: list[str] = Field(default_factory=list)
    min_confidence: float = Field(default=0.3)
    entry_types: list[str] = Field(default_factory=lambda: ["skill", "experience"])
    exclude_thread_ids: list[str] = Field(default_factory=list)  # privacy boundary
```

### Tests

- Push: local events sent to peer, peer's last_sync_clock updated
- Pull: foreign events applied, own instance events skipped (cycle prevention)
- Validation feedback: success → peer trust increases, failure → decreases
- Replication filter: domain allowlist filters entries
- Replication filter: exclude_thread_ids respected (privacy boundary)

---

## C9. PROV-JSONLD Lite schema + ColonyTranscriptView

### Provenance schema

Create `docs/schemas/formicos-prov-context.jsonld`:
```json
{
  "@context": {
    "prov": "http://www.w3.org/ns/prov#",
    "formicos": "https://formicos.dev/ns/",
    "generated_by": "prov:wasGeneratedBy",
    "attributed_to": "prov:wasAttributedTo",
    "derived_from": "prov:wasDerivedFrom",
    "generated_at": "prov:generatedAtTime"
  }
}
```

In `core/types.py`:
```python
class ProvenanceChain(BaseModel):
    model_config = ConfigDict(frozen=True)
    generated_by: str = Field(..., description="thread_id + step")
    attributed_to: str = Field(..., description="instance_id or colony_id")
    derived_from: list[str] = Field(default_factory=list, description="Source entry IDs")
    generated_at: str = Field(..., description="ISO timestamp")

class KnowledgeExchangeEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry_id: str
    content: str
    entry_type: str
    polarity: str
    domains: list[str]
    observation_crdt: dict[str, Any]  # serialized ObservationCRDT
    provenance: ProvenanceChain
    exchange_hop: int = 0
    decay_class: str = "ephemeral"
```

### ColonyTranscriptView

Create `surface/transcript_view.py`:
```python
"""Canonical colony transcript schema for export and federation exchange."""

class RoundView(BaseModel):
    round_number: int
    agents: list[AgentTurnView]
    convergence: float
    cost: float
    duration_ms: int

class AgentTurnView(BaseModel):
    agent_id: str
    caste: str
    output_summary: str
    tool_calls: list[str]
    input_tokens: int
    output_tokens: int

class ColonyStats(BaseModel):
    total_rounds: int
    total_cost: float
    total_duration_ms: int
    skills_extracted: int

class ArtifactView(BaseModel):
    type: str
    content_preview: str

class ColonyTranscriptView(BaseModel):
    colony_id: str
    thread_id: str
    workspace_id: str
    task: str
    strategy: str
    castes: list[str]
    rounds: list[RoundView]
    artifacts: list[ArtifactView]
    knowledge_used: list[str]
    knowledge_produced: list[str]
    stats: ColonyStats

def build_colony_transcript_view(colony_proj: Any, projections: Any) -> ColonyTranscriptView:
    """Build canonical transcript from colony projection."""
    # Credential redaction runs here (imports from credential_scan if available)
    ...

def transcript_to_a2a_artifact(view: ColonyTranscriptView) -> dict[str, Any]:
    """Convert to A2A DataPart artifact format."""
    ...

def transcript_to_mcp_resource(view: ColonyTranscriptView) -> dict[str, Any]:
    """Convert to MCP resource format."""
    ...
```

### Tests

- ColonyTranscriptView builds from projection data
- Transcript adapters produce valid A2A and MCP formats
- ProvenanceChain serializes with PROV field names
- KnowledgeExchangeEntry roundtrips through JSON

---

## Validation

Run after all changes:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

**Critical checks:**
- `core/crdt.py` and `core/vector_clock.py` must NOT import from surface or engine
- `core/types.py` additions must not import from surface
- `core/events.py` import-time self-check must pass (manifest matches union)
- `adapters/federation_transport.py` imports from core only
- `surface/trust.py`, `surface/federation.py`, `surface/conflict_resolution.py` import from core (OK) and surface (OK)
- No backward imports (engine→surface, core→engine, etc.)
