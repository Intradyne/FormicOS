# Federation Implementation Reference

Current-state reference for FormicOS federation: CRDT primitives, push/pull
replication, Bayesian peer trust, conflict resolution, hop-aware retrieval
penalties, and vector clocks. Code-anchored to Wave 59.

---

## CRDT Primitives (`core/crdt.py`)

Four primitives compose the `ObservationCRDT`:

### GCounter (Grow-only counter)

Per-node observation counts. Merge: pairwise max across all node keys.
Value: sum of all counts. Only positive deltas.

### LWWRegister (Last-Writer-Wins)

Single value with timestamp. Merge: higher timestamp wins; ties broken
by `node_id` (lexicographic). Used for content, entry_type, decay_class.

### GSet (Grow-only set)

Elements never removed. Merge: union. Used for domains and archived_by.

### ObservationCRDT Composite

```python
class ObservationCRDT:
    successes: GCounter        # positive observations
    failures: GCounter         # negative observations
    last_obs_ts: dict[str, LWWRegister]  # per-instance last-observation
    archived_by: GSet          # instance IDs that archived this entry
    content: LWWRegister       # entry content (LWW)
    entry_type: LWWRegister    # skill/experience (LWW)
    domains: GSet              # domain tags (grow-only)
    decay_class: LWWRegister   # confidence decay rate (LWW)
```

All components merge independently using their own semantics. Result is
deterministic and order-independent (commutative, associative, idempotent).

### Gamma-Decay at Query Time

Decay is applied at query time, NOT stored in the CRDT.

```python
def query_alpha(self, now, gamma_rates, prior_alpha, max_elapsed_days=180.0) -> float
def query_beta(self, now, gamma_rates, prior_beta, max_elapsed_days=180.0) -> float
def query_confidence(self, now, gamma_rates, prior_alpha, prior_beta) -> float
```

Formula: `alpha = prior_alpha + sum(gamma^elapsed_days * count)` per instance.
Elapsed days capped at 180 (ADR-041 hardening). Confidence = posterior mean
`alpha / (alpha + beta)`.

Gamma rates: `ephemeral=0.98` (~34-day half-life), `stable=0.995`
(~139-day half-life), `permanent=1.0` (no decay).

---

## Federation Protocol (`surface/federation.py`)

### PeerConnection

Fields: `instance_id`, `endpoint` (HTTP), `trust` (PeerTrust object),
`replication_filter`, `last_sync_clock` (VectorClock).

### FederationManager

**Push**: Get events since peer's `last_sync_clock`, apply replication
filter, send via transport, update peer's sync clock.

```python
async def push_to_peer(self, peer_id: str) -> int  # returns events sent
```

**Pull**: Request events from peer's endpoint, check for cycles (instance_id
match), apply to local projection.

```python
async def pull_from_peer(self, peer_id: str) -> int  # returns events applied
```

**Validation feedback**: Report outcome of using foreign knowledge to
originating peer. Success: +1 alpha. Failure: +2.0 beta (asymmetric penalty).

```python
async def send_validation_feedback(self, peer_id: str, entry_id: str, success: bool) -> None
```

### Foreign Event Application

Foreign events are stamped with `source_peer` and incremented
`federation_hop`. CRDT components merge pairwise.

### Replication Filter

```python
class ReplicationFilter:
    domain_allowlist: list[str]      # only these domains
    min_confidence: float            # threshold
    entry_types: list[str]           # skill|experience
    exclude_thread_ids: list[str]    # privacy boundary
```

---

## Peer Trust (`surface/trust.py`)

### PeerTrust

Bayesian confidence using Beta distribution posteriors.

```python
@dataclass
class PeerTrust:
    alpha: float = 1.0   # successes + 1
    beta: float = 1.0    # failures + 1
```

**Trust score**: 10th percentile of Beta posterior (not mean). Penalizes
uncertainty — requires ~30+ successes for 0.8 trust.

```python
@property
def score(self) -> float:
    return _beta_ppf_approx(0.10, self.alpha, self.beta)
```

**Asymmetric updates**: `record_success()` adds +1.0 to alpha.
`record_failure()` adds +2.0 to beta (Wave 38 hardening).

**Trust decay**: `gamma=0.9995` per day. Retains 91.4% at 90 days,
83.5% at 180 days. Decays toward prior (1.0, 1.0).

### Hop-Aware Trust Discount

```python
def trust_discount(trust_score: float, hop: int = 0) -> float:
    hop_base = 0.6 + 0.25 * trust_score  # range [0.6, 0.85]
    raw = trust_score * (hop_base ** hop)
    return min(raw, 0.5)  # cap: federated never outweighs local
```

High-trust peers decay slower per hop; low-trust peers decay faster.
Maximum 0.5 — federated knowledge never outweighs local verified.

### Federated Retrieval Penalty

```python
def federated_retrieval_penalty(
    entry: dict[str, Any],
    local_verified_max_score: float = 0.0,
    *, peer_trust_score: float | None = None,
) -> float
```

Three-signal blend:
1. **Entry confidence posterior** (10th percentile of Beta).
2. **Status floor**: verified=0.80, active=0.55, candidate=0.35, stale=0.20.
3. **Hop-aware trust discount**.

Computation: `blended = 0.6 * posterior + 0.4 * floor`. If federated:
`blended = min(blended, hop_discount + 0.1)`. Bounded to [0.1, 0.9].

Applied in knowledge_catalog.py as composite score multiplier:
`raw_composite * fed_penalty`.

---

## Conflict Resolution (`surface/conflict_resolution.py`)

### Pair Classification

```python
def classify_pair(
    entry_a: dict[str, Any], entry_b: dict[str, Any],
    *, overlap_threshold: float = 0.3,
) -> ClassifiedPair | None
```

Rules:
1. **Contradiction**: Opposite polarity + domain overlap >= threshold.
2. **Temporal update**: Same type + high overlap (>= 0.5) + different timestamps.
3. **Complement**: Overlapping domains, compatible polarity.

### Detection

```python
def detect_contradictions(
    entries: dict[str, dict[str, Any]], *,
    status_filter: set[str] | None = None,
    min_alpha: float = 0.0,
    overlap_threshold: float = 0.3,
) -> list[ClassifiedPair]
```

Used by maintenance.py and proactive_intelligence.py.

### Three-Phase Resolution

```python
def resolve_classified(
    entry_a: dict[str, Any], entry_b: dict[str, Any],
    classification: ClassifiedPair | None = None,
) -> ConflictResult
```

**Phase 1 — Pareto Dominance**: Counts criteria where A dominates B
(posterior mean margin > 0.15, recency margin > 0.2, provenance count
differs by > 1). If >= 2 criteria: winner declared.

**Phase 2 — Composite Threshold**: Score = `0.5 * mean + 0.3 * recency +
0.2 * provenance`. Adaptive threshold: `0.05 + 2.0 / max(avg_obs, 1.0)`.
Tighter when both entries have more observations.

**Phase 3 — Competing Hypotheses**: Scores too close. Both entries retained
as `Resolution.competing`.

### Resolution Enum

```python
class Resolution(StrEnum):
    winner = "winner"               # clear winner
    competing = "competing"         # too close to call
    complement = "complement"       # co-usable, Wave 42
    temporal_update = "temporal_update"  # newer supersedes, Wave 42
```

### ConflictResult

Fields: `resolution`, `primary_id`, `secondary_id`, `primary_score`,
`secondary_score`, `method` (pareto/threshold/competing/complement/
temporal_update), `detail`.

---

## Federation Events (CRDT Operations)

Four event types for CRDT state changes (ADR-042):

| Event | Semantics |
|-------|-----------|
| `CRDTCounterIncremented` | G-Counter increment (field: successes/failures) |
| `CRDTTimestampUpdated` | LWW Register update (per-instance observation time) |
| `CRDTSetElementAdded` | G-Set element addition (domains/archived_by) |
| `CRDTRegisterAssigned` | LWW Register assignment (content/entry_type/decay_class) |

Plus `MemoryEntryMerged` for both dedup and federation conflict resolution.

---

## Vector Clocks (`core/vector_clock.py`)

Causal ordering for federated instances:

```python
@dataclass
class VectorClock:
    clock: dict[str, int]

    def increment(self, instance_id: str) -> VectorClock
    def merge(self, other: VectorClock) -> VectorClock  # pairwise max
    def happens_before(self, other: VectorClock) -> bool
    def is_concurrent(self, other: VectorClock) -> bool
```

Used by `PeerConnection.last_sync_clock` to track replication progress.
Push/pull requests include the clock; events since that point are transmitted.

---

## ProvenanceChain (`core/types.py`)

```python
class ProvenanceChain(BaseModel):
    generated_by: str        # thread_id + step
    attributed_to: str       # instance_id or colony_id
    derived_from: list[str]  # source entry IDs
    generated_at: str        # ISO timestamp
```

Used in `KnowledgeExchangeEntry` for federation exchange serialization.

---

## Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| `PRIOR_ALPHA` | 5.0 | `knowledge_constants.py` |
| `PRIOR_BETA` | 5.0 | `knowledge_constants.py` |
| `MAX_ELAPSED_DAYS` | 180.0 | `knowledge_constants.py` |
| Trust failure penalty | +2.0 beta | `trust.py` |
| Hop discount base | `0.6 + 0.25 * trust_score` | `trust.py` |
| Hop discount cap | 0.5 | `trust.py` |
| Federated penalty bounds | [0.1, 0.9] | `trust.py` |
| Trust decay gamma | 0.9995/day | `trust.py` |
| Pareto mean margin | > 0.15 | `conflict_resolution.py` |
| Pareto recency margin | > 0.2 | `conflict_resolution.py` |
| Composite threshold base | 0.05 | `conflict_resolution.py` |

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/crdt.py` | ObservationCRDT, GCounter, LWWRegister, GSet |
| `core/vector_clock.py` | VectorClock for causal ordering |
| `core/types.py` | Resolution, ProvenanceChain, ReplicationFilter |
| `surface/federation.py` | FederationManager, push/pull replication |
| `surface/trust.py` | PeerTrust, hop discount, retrieval penalty |
| `surface/conflict_resolution.py` | classify_pair, detect_contradictions, resolve_classified |
| `surface/knowledge_catalog.py` | Penalty application in composite scoring |
| `surface/knowledge_constants.py` | PRIOR_ALPHA/BETA, GAMMA_RATES |
| `adapters/federation_transport.py` | A2A transport layer |
