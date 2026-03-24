# Coordination, Context, and Knowledge Math Map

Grounded against the live FormicOS codebase on 2026-03-19.

This document is a code-anchored starting point for research on the math and
algorithms behind coordination, context assembly, and shared knowledge.

## Fast Reading Order

1. `src/formicos/surface/knowledge_catalog.py`
2. `src/formicos/surface/colony_manager.py`
3. `src/formicos/engine/runner.py`
4. `src/formicos/engine/strategies/stigmergic.py`
5. `src/formicos/engine/context.py`
6. `src/formicos/surface/proactive_intelligence.py`
7. `src/formicos/surface/trust.py`
8. `src/formicos/surface/conflict_resolution.py`

Then read:

1. `docs/decisions/041-knowledge-tuning.md`
2. `docs/decisions/044-cooccurrence-scoring.md`
3. `docs/decisions/011-quality-scoring.md`
4. `docs/decisions/017-bayesian-confidence-dedup.md`
5. `docs/decisions/008-context-window-management.md`

## At A Glance

There are three different math systems in the repo:

1. `Coordination math`
   - dynamic routing between agents within a colony
   - convergence scoring
   - pheromone update dynamics
   - DAG validation for parallel execution plans
2. `Context math`
   - token budgeting
   - compaction heuristics
   - retrieval packing
   - a legacy UCB-scored skill path
3. `Knowledge math`
   - Beta confidence posteriors
   - Thompson-sampled retrieval
   - query-time gamma decay
   - co-occurrence reinforcement
   - trust / admission / conflict handling
   - maintenance and branching diagnostics

The most research-sensitive part of FormicOS is not the context budget code.
It is the interaction between the knowledge system and the coordination system.

## 1. Coordination Math

### 1.1 Dynamic topology generation

Primary file:

- `src/formicos/engine/strategies/stigmergic.py`

Core snippet:

```python
async def resolve_topology(
    self,
    agents: Sequence[AgentConfig],
    context: ColonyContext,
    pheromone_weights: PheromoneWeights | None = None,
) -> list[list[str]]:
    n = len(agents)

    queries = [f"I need help with: {a.recipe.name} tasks" for a in agents]
    keys = [
        f"I can help with: {a.recipe.name} - {a.recipe.description}"
        for a in agents
    ]

    embeddings = await self._get_embeddings(queries + keys)
    query_vecs = embeddings[:n]
    key_vecs = embeddings[n:]

    sim_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                sim_matrix[i][j] = _dot(query_vecs[i], key_vecs[j])

    if pheromone_weights:
        for (src, tgt), weight in pheromone_weights.items():
            i = _agent_index(src, agents)
            j = _agent_index(tgt, agents)
            if i is not None and j is not None:
                sim_matrix[i][j] *= weight

    adjacency = [
        [1 if sim_matrix[i][j] >= self._tau else 0 for j in range(n)]
        for i in range(n)
    ]

    for j in range(n):
        inbound = [
            (sim_matrix[i][j], i) for i in range(n) if adjacency[i][j] == 1
        ]
        if len(inbound) > self._k_in:
            inbound.sort(reverse=True)
            keep = {i for _, i in inbound[: self._k_in]}
            for i in range(n):
                if adjacency[i][j] == 1 and i not in keep:
                    adjacency[i][j] = 0

    order = _topological_sort(adjacency, n, sim_matrix)
    groups = _collapse_into_groups(adjacency, order, n)
    return [[agents[i].id for i in group] for group in groups]
```

What the math is doing:

- `embedded semantic need/offer matching` creates a weighted directed graph
- `pheromone_weights` act multiplicatively, not additively
- `tau` is a hard threshold on weighted similarity
- `k_in` is a hard sparsity cap on inbound degree
- the final execution schedule is produced by topological grouping

Why this matters:

- it is already a form of dynamic graph construction
- the graph is not learned end-to-end; it is assembled from heuristics
- the pheromone system influences graph selection only through multiplicative
  edge scaling

Research directions most likely to help:

- dynamic sparse graph learning for multi-agent systems
- ACO / MMAS anti-stagnation controls
- communication topology optimization for LLM agents
- uncertainty-aware graph priors

Relevant tests:

- `tests/unit/engine/test_strategies.py`

### 1.2 Cycle breaking and execution grouping

The topology code uses Kahn-style topological sorting with cycle breaking:

```python
def _topological_sort(
    adjacency: list[list[int]],
    n: int,
    sim_matrix: list[list[float]],
) -> list[int]:
    adj = [row[:] for row in adjacency]
    in_degree = [sum(adj[i][j] for i in range(n)) for j in range(n)]
    queue: deque[int] = deque()
    for i in range(n):
        if in_degree[i] == 0:
            queue.append(i)

    order: list[int] = []
    while len(order) < n:
        if not queue:
            remaining = [i for i in range(n) if i not in set(order)]
            min_weight = math.inf
            min_edge: tuple[int, int] = (remaining[0], remaining[0])
            for i in remaining:
                for j in remaining:
                    if adj[i][j] == 1 and sim_matrix[i][j] < min_weight:
                        min_weight = sim_matrix[i][j]
                        min_edge = (i, j)
            src, tgt = min_edge
            adj[src][tgt] = 0
            in_degree[tgt] -= 1
            if in_degree[tgt] == 0:
                queue.append(tgt)
            continue
```

This resolves cycles by removing the lowest-weight edge among the remaining
nodes. It is simple and explainable, but still heuristic.

Research directions:

- minimum feedback arc set approximations
- graph pruning under noisy edge weights
- topological scheduling under uncertain precedence relations

### 1.3 Convergence and governance scoring

Primary file:

- `src/formicos/engine/runner.py`

Core snippet:

```python
goal_alignment = _cosine_similarity(goal_vec, curr_vec)
stability = _cosine_similarity(prev_vec, curr_vec)
prev_alignment = _cosine_similarity(prev_vec, goal_vec)
progress = max(0.0, goal_alignment - prev_alignment)

score = (
    0.4 * goal_alignment
    + 0.3 * stability
    + 0.3 * min(1.0, progress * 5.0)
)
is_stalled = stability > 0.95 and progress < 0.01 and round_number > 2
is_converged = score > 0.85 and stability > 0.90
```

This drives:

- warning behavior
- stall detection
- colony completion behavior
- pheromone reward/penalty updates
- downstream quality scoring

Research directions:

- convergence diagnostics in iterative optimization
- stopping criteria for multi-agent deliberation
- semantic fixed-point detection
- confidence-calibrated stopping rules

### 1.4 Pheromone update dynamics

Primary file:

- `src/formicos/engine/runner.py`

Core snippet:

```python
def _update_pheromones(
    weights: PheromoneWeights | None,
    active_edges: Sequence[tuple[str, str]],
    governance_action: str,
    convergence_progress: float,
) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    if weights:
        for edge, w in weights.items():
            result[edge] = 1.0 + (w - 1.0) * _EVAPORATE

    should_strengthen = governance_action == "continue" and convergence_progress > 0
    should_weaken = governance_action in ("halt", "force_halt", "warn")
    for edge in active_edges:
        current = result.get(edge, 1.0)
        if should_strengthen:
            current *= _STRENGTHEN
        elif should_weaken:
            current *= _WEAKEN
        result[edge] = max(_LOWER, min(_UPPER, current))
    return result
```

What it implies:

- evaporation is toward neutral `1.0`, not toward zero
- reinforcement depends on governance action plus positive progress
- updates are bounded

Research directions:

- adaptive evaporation schedules
- delayed credit assignment for communication edges
- bandit or Bayesian updates over edge usefulness
- entropy-aware anti-saturation controls

### 1.5 Knowledge priors feeding topology

Primary file:

- `src/formicos/engine/runner.py`

This is the seam where the long-term knowledge system first touches the
short-term communication graph.

Core snippet:

```python
def _compute_knowledge_prior(
    agents: Sequence[AgentConfig],
    knowledge_items: list[dict[str, Any]] | None,
) -> dict[tuple[str, str], float] | None:
    domain_stats: dict[str, list[float]] = {}
    for item in knowledge_items:
        alpha = float(item.get("conf_alpha", 5.0))
        beta = float(item.get("conf_beta", 5.0))
        posterior_mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
        if alpha + beta < 3.0:
            continue
        for d in item.get("domains", []):
            domain_stats.setdefault(d, []).append(posterior_mean)

    ...

    bias = _PRIOR_MIN + combined * (_PRIOR_MAX - _PRIOR_MIN)
```

Why this is a high-leverage research seam:

- the current mapping from knowledge to topology is domain-name overlap plus
  posterior mean averaging
- that is useful, but not yet principled
- if you are looking for one place where a paper could materially change the
  architecture, this is one of the best candidates

Research directions:

- belief-informed routing
- uncertainty-aware communication priors
- graph initialization from shared memory
- task graph induction from prior successful decompositions

### 1.6 Parallel planning math

Primary file:

- `src/formicos/surface/queen_tools.py`

Core snippet:

```python
def _validate_dag(tasks: list[Any]) -> bool:
    task_ids = {t.task_id for t in tasks}
    adj: dict[str, list[str]] = {t.task_id: [] for t in tasks}
    in_degree: dict[str, int] = {t.task_id: 0 for t in tasks}
    for t in tasks:
        for dep in t.depends_on:
            if dep in task_ids:
                adj[dep].append(t.task_id)
                in_degree[t.task_id] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited == len(task_ids)
```

This is less mathematically deep than the stigmergic layer, but still relevant
for coordination research around:

- task graph decomposition
- critical-path optimization
- adaptive batching of independent work

## 2. Context Math

### 2.1 Tier budgets and regime injection

Primary file:

- `src/formicos/engine/context.py`

Core snippet:

```python
class TierBudgets(BaseModel):
    goal: int = 500
    routed_outputs: int = 1500
    max_per_source: int = 500
    merge_summaries: int = 500
    prev_round_summary: int = 500
    skill_bank: int = 800
    compaction_threshold: int = 500
```

And:

```python
class BudgetRegime:
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    CRITICAL = "CRITICAL"

    @staticmethod
    def classify(remaining_pct: float) -> str:
        if remaining_pct >= 70.0:
            return BudgetRegime.HIGH
        if remaining_pct >= 30.0:
            return BudgetRegime.MEDIUM
        if remaining_pct >= 10.0:
            return BudgetRegime.LOW
        return BudgetRegime.CRITICAL
```

The context system is a manually tiered allocation system with:

- per-tier caps
- per-source caps
- edge-preserving truncation
- budget-state prompt injection

### 2.2 Compaction heuristic

Core snippet:

```python
def _compact_summary(text: str, goal: str, budget_tokens: int) -> str:
    sentences = _split_sentences(text)
    goal_words = set(goal.lower().split())

    scored: list[tuple[int, float, str]] = []
    for i, sent in enumerate(sentences):
        sent_words = set(sent.lower().split())
        overlap = len(goal_words & sent_words)
        position_bonus = 0.5 if (i == 0 or i == len(sentences) - 1) else 0.0
        score = overlap + position_bonus
        scored.append((i, score, sent))

    scored.sort(key=lambda x: -x[1])
```

What it is:

- query-focused extractive summarization
- sentence-level greedy packing
- lexical overlap plus edge-position bonus

What it is not:

- submodular selection
- learned summarization
- novelty-aware packing
- uncertainty-aware information selection

Research directions:

- budgeted maximum coverage
- MMR / diversity-aware selection
- submodular context packing
- query-focused summarization for constrained LLM prompts

### 2.3 Legacy retrieval scoring in the context path

This is important because FormicOS has two different retrieval math stacks.

The older context path still uses UCB-style exploration:

```python
semantic = 1.0 - min(hit.score, 1.0)
confidence = float(hit.metadata.get("confidence", 0.5))
freshness = _compute_freshness(hit.metadata.get("extracted_at", ""))

alpha = float(hit.metadata.get("conf_alpha", 0))
beta_p = float(hit.metadata.get("conf_beta", 0))
n_obs = max(alpha + beta_p - 2.0, 1.0) if alpha > 0 else 1.0
big_n = max(total_colonies, 1)
exploration = ucb_exploration_weight * math.sqrt(math.log(big_n) / n_obs)

composite = (
    0.50 * semantic
    + 0.25 * confidence
    + 0.20 * freshness
    + 0.05 * min(exploration, 1.0)
)
```

Meanwhile the newer knowledge path uses Thompson sampling. That means the repo
currently contains both:

- UCB-style exploration in `engine/context.py`
- Thompson-sampled retrieval in `surface/knowledge_catalog.py`

Research target:

- unified nonstationary bandit retrieval under delayed feedback

Relevant tests:

- `tests/unit/engine/test_ucb_scoring.py`
- `tests/unit/engine/test_context_tiers.py`

## 3. Knowledge Math

### 3.1 Constants and global tuning

Primary file:

- `src/formicos/surface/knowledge_constants.py`

Core snippet:

```python
GAMMA_PER_DAY: float = 0.98
PRIOR_ALPHA: float = 5.0
PRIOR_BETA: float = 5.0
MAX_ELAPSED_DAYS: float = 180.0

GAMMA_RATES: dict[str, float] = {
    "ephemeral": 0.98,
    "stable": 0.995,
    "permanent": 1.0,
}

COMPOSITE_WEIGHTS: dict[str, float] = {
    "semantic": 0.38,
    "thompson": 0.25,
    "freshness": 0.15,
    "status": 0.10,
    "thread": 0.07,
    "cooccurrence": 0.05,
}
```

This file is the numerical center of gravity for the knowledge system.

### 3.2 Composite retrieval scoring

Primary file:

- `src/formicos/surface/knowledge_catalog.py`

Core snippet:

```python
thompson = random.betavariate(max(alpha, 0.1), max(beta_p, 0.1))
freshness = _compute_freshness(item.get("created_at", ""))
status_bonus = _STATUS_BONUS.get(str(item.get("status", "")), 0.0)
thread_bonus = float(item.get("_thread_bonus", 0.0))
cooc = cooc_scores.get(item.get("id", ""), 0.0)
fed_penalty = federated_retrieval_penalty(item)

raw_composite = (
    _W["semantic"] * semantic
    + _W["thompson"] * thompson
    + _W["freshness"] * freshness
    + _W["status"] * status_bonus
    + _W["thread"] * thread_bonus
    + _W["cooccurrence"] * cooc
    + pin_boost
)
composite = -(raw_composite * fed_penalty)
```

Signals in play:

- semantic relevance
- Thompson draw from Beta posterior
- freshness decay
- status bonus
- thread-local bonus
- co-occurrence
- federated penalty
- operator pin boost

Research directions:

- nonstationary Thompson sampling
- delayed-reward bandits
- calibration of stochastic rankers
- diversity-aware retrieval under posterior uncertainty
- trust-aware rank aggregation

Relevant tests:

- `tests/unit/surface/test_scoring_invariants.py`
- `tests/unit/surface/test_cooccurrence_scoring.py`
- `tests/unit/surface/test_thompson_sampling.py`

### 3.3 Co-occurrence normalization

Core snippet:

```python
def _sigmoid_cooccurrence(raw_weight: float) -> float:
    if raw_weight <= 0.0:
        return 0.0
    return 1.0 - math.exp(-0.6 * raw_weight)
```

And:

```python
def _cooccurrence_score(entry_id: str, other_ids: list[str], projections: Any) -> float:
    max_weight = 0.0
    for other_id in other_ids:
        key = cooccurrence_key(entry_id, other_id)
        entry = projections.cooccurrence_weights.get(key)
        if entry:
            max_weight = max(max_weight, entry.weight)
    return _sigmoid_cooccurrence(max_weight)
```

This means:

- raw reinforcement can accumulate
- retrieval consumes a bounded nonlinear transform
- the score uses `max cluster connection`, not sum or average

Research directions:

- graph centrality vs max-edge use in retrieval
- Hebbian-style association metrics
- cluster-aware ranking under uncertainty

### 3.4 Query-time decay in the federated CRDT

Primary file:

- `src/formicos/core/crdt.py`

Core snippet:

```python
def query_alpha(
    self,
    now: float,
    gamma_rates: dict[str, float],
    prior_alpha: float,
    max_elapsed_days: float = 180.0,
) -> float:
    dc = self.decay_class.value if self.decay_class.value else "ephemeral"
    gamma = gamma_rates.get(dc, 0.98)
    alpha = prior_alpha
    for inst_id, count in self.successes.counts.items():
        ts_reg = self.last_obs_ts.get(inst_id)
        ts = ts_reg.timestamp if ts_reg else now
        elapsed = min((now - ts) / 86400.0, max_elapsed_days)
        alpha += (gamma ** max(elapsed, 0.0)) * count
    return max(alpha, 1.0)
```

And symmetric logic for `query_beta()`.

This is one of the most important design decisions in the repo:

- raw observations are monotonic CRDT facts
- decay is not stored
- effective confidence is computed at read time

Research directions:

- computational CRDTs
- decayed evidence accumulation
- trust-weighted replicated belief systems

### 3.5 Outcome-weighted confidence updates

Primary file:

- `src/formicos/surface/colony_manager.py`

Core snippet:

```python
gamma = GAMMA_RATES.get(decay_class, GAMMA_PER_DAY)
gamma_eff = gamma ** elapsed_days
decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
decayed_beta = gamma_eff * old_beta + (1 - gamma_eff) * PRIOR_BETA

if succeeded:
    delta_alpha = min(max(0.5 + quality_score, 0.5), 1.5)
    new_alpha = max(decayed_alpha + delta_alpha, 1.0)
    new_beta = max(decayed_beta, 1.0)

    peak_alpha = float(entry.get("peak_alpha", entry.get("conf_alpha", PRIOR_ALPHA)))
    if decayed_alpha < peak_alpha * 0.5 and decay_class in ("stable", "permanent"):
        gap = peak_alpha - decayed_alpha
        restoration = gap * 0.2
        new_alpha += restoration
else:
    failure_penalty = 1.0 - quality_score
    delta_beta = min(max(0.5 + failure_penalty, 0.5), 1.5)
    new_alpha = max(decayed_alpha, 1.0)
    new_beta = max(decayed_beta + delta_beta, 1.0)
```

This includes:

- time-based decay before update
- quality-dependent reinforcement
- quality-dependent failure penalties
- mastery restoration for previously strong stable/permanent knowledge

Research directions:

- discounted Bayesian updating
- nonstationary evidence models
- confidence restoration under dormancy
- delayed success attribution

Relevant tests:

- `tests/unit/surface/test_bayesian_confidence.py`
- `tests/unit/surface/test_gamma_decay.py`
- `tests/unit/surface/test_mastery_restoration.py`

### 3.6 Retrieval-time bookkeeping that already behaves like weak feedback

There are two small but important feedback loops already in retrieval:

```python
if raw_semantic < 0.38:
    proj["prediction_error_count"] = prev + 1
```

And:

```python
if co_entry is None:
    co_entry = CooccurrenceEntry(
        weight=0.5, last_reinforced=now_iso, reinforcement_count=1,
    )
else:
    co_entry.weight = min(co_entry.weight * 1.05, 10.0)
```

That means search itself is already changing:

- prediction-error signals
- co-occurrence structure

This is a low-grade online learning loop, not just read-only retrieval.

### 3.7 Admission scoring

Primary file:

- `src/formicos/surface/admission.py`

Core snippet:

```python
_WEIGHTS: dict[str, float] = {
    "confidence": 0.20,
    "provenance": 0.15,
    "scanner": 0.25,
    "federation": 0.10,
    "observation_mass": 0.10,
    "content_type": 0.10,
    "recency": 0.10,
}

posterior_mean = alpha / (alpha + beta_val) if alpha > 0 and beta_val > 0 else 0.5
certainty = 1.0 - math.exp(-0.05 * total_obs) if total_obs > 0 else 0.0
fed_score = peer_trust_score * 0.8 if peer_trust_score is not None else 0.3
composite = sum(_WEIGHTS[k] * signal_scores[k] for k in _WEIGHTS)
```

And the decision thresholds:

```python
if scan_tier in ("high", "critical"):
    return False, "rejected"
if score < 0.25:
    return False, "rejected"
if is_federated and score < 0.40:
    return True, "candidate"
if score < 0.35:
    return True, "candidate"
return True, ""
```

This is effectively a hand-built risk scoring model.

Research directions:

- reputation systems
- calibrated trust/risk scoring
- evidence fusion
- anomaly or poisoning resistance for shared memory systems

### 3.8 Federation trust

Primary file:

- `src/formicos/surface/trust.py`

Core snippet:

```python
@dataclass
class PeerTrust:
    alpha: float = 1.0
    beta: float = 1.0

    @property
    def score(self) -> float:
        return _beta_ppf_approx(0.10, self.alpha, self.beta)

    def record_success(self) -> None:
        self.alpha += 1.0

    def record_failure(self) -> None:
        self.beta += 2.0
```

And:

```python
def trust_discount(trust_score: float, hop: int = 0) -> float:
    raw = trust_score * (0.7 ** hop)
    return min(raw, 0.5)
```

And:

```python
def federated_retrieval_penalty(entry: dict[str, Any], local_verified_max_score: float = 0.0) -> float:
    source_peer = entry.get("source_peer", "")
    if not source_peer:
        return 1.0
    status = str(entry.get("status", "candidate"))
    if status == "verified":
        return 0.85
    if status == "active":
        return 0.65
    return 0.45
```

Important note:

- `federated_retrieval_penalty()` is wired into retrieval today
- `trust_discount()` appears defined but not currently used elsewhere in `src`

That suggests a live research/design question:

`Should the retrieval penalty be driven directly by peer posterior trust instead of coarse status bands?`

Relevant tests:

- `tests/unit/surface/test_trust.py`
- `tests/unit/surface/test_wave38_federation_trust.py`

### 3.9 Conflict resolution

Primary file:

- `src/formicos/surface/conflict_resolution.py`

Core snippet:

```python
ev_a = entry_a.get("conf_alpha", 5) + entry_a.get("conf_beta", 5) - 10
ev_b = entry_b.get("conf_alpha", 5) + entry_b.get("conf_beta", 5) - 10
rec_a = _recency_score(entry_a)
rec_b = _recency_score(entry_b)
prov_a = len(entry_a.get("merged_from", []))
prov_b = len(entry_b.get("merged_from", []))

score_a = 0.6 * _normalize(ev_a) + 0.2 * rec_a + 0.2 * _normalize(prov_a)
score_b = 0.6 * _normalize(ev_b) + 0.2 * rec_b + 0.2 * _normalize(prov_b)

avg_evidence = (max(ev_a, 1) + max(ev_b, 1)) / 2
threshold = 0.05 + 2.0 / avg_evidence
```

This is currently one of the weakest mathematical seams in the system.

Why:

- recency is not really time-aware enough
- evidence and provenance are collapsed into a simple linear score
- contradiction resolution is not yet a full temporal belief revision model

If you want a paper area likely to produce a noticeable algorithm upgrade,
belief revision and evidence arbitration are excellent candidates.

Relevant tests:

- `tests/unit/surface/test_conflict_resolution.py`

## 4. Maintenance And Diagnostics Math

### 4.1 Stale detection

Primary file:

- `src/formicos/surface/maintenance.py`

Core logic:

```python
is_stale_by_age = entry_id not in accessed_ids and age > timedelta(days=stale_days)
is_stale_by_prediction = prediction_errors >= 5 and access_count < 3
```

This combines:

- non-use over time
- repeated low-relevance retrievals

That is a useful heuristic blend of aging and retrieval failure.

### 4.2 Co-occurrence decay and distillation candidates

Core snippet:

```python
_COOCCURRENCE_GAMMA_PER_DAY: float = 0.995
_COOCCURRENCE_PRUNE_THRESHOLD: float = 0.1

gamma_eff = _COOCCURRENCE_GAMMA_PER_DAY ** elapsed_days
entry.weight *= gamma_eff

if entry.weight < _COOCCURRENCE_PRUNE_THRESHOLD:
    to_prune.append(key)
```

And cluster distillation:

```python
if w <= 2.0:
    continue

if len(cluster) < 5:
    continue

if cluster_edges and sum(cluster_edges) / len(cluster_edges) > 3.0:
    candidates.append(sorted(cluster))
```

This is graph maintenance and graph compression, not just retrieval tuning.

Research directions:

- graph sparsification with retention guarantees
- temporal community detection
- memory consolidation and abstraction

### 4.3 Branching-factor stagnation diagnostics

Primary file:

- `src/formicos/surface/proactive_intelligence.py`

Core snippet:

```python
def _effective_count(weights: list[float]) -> float:
    total = sum(weights)
    probs = [w / total for w in weights if w > 0]
    entropy = -sum(p * math.log(p) for p in probs)
    return math.exp(entropy)
```

And:

```python
low_topo = topo_bf < 2.0 and topo_bf > 0
low_know = know_bf < 3.0 and len(entries) >= 5
low_config = config_bf < 1.5 and total_count >= 5

stagnation_signals = sum([low_topo, low_know, low_config])
if stagnation_signals < 2:
    return insights
if failure_rate < 0.3:
    return insights
```

This is effectively using `exp(H)` as an effective branching count across:

- topology weights
- knowledge posterior mass
- colony configuration diversity

That is a strong seam for connecting ACO stagnation theory to the codebase.

Relevant tests:

- `tests/unit/surface/test_wave37_branching.py`

### 4.4 Evaporation recommendations

Core logic:

```python
if current_class in ("stable", "permanent") and (
    avg_errors >= 3.0
    or demotion_rate >= 0.4
    or (avg_conf < 0.4 and len(d_entries) >= 5)
):
    recommended = "ephemeral" if current_class == "stable" else "stable"

if current_class == "ephemeral" and (
    avg_errors < 1.0
    and avg_conf >= 0.7
    and demotion_rate < 0.1
    and len(d_entries) >= 5
):
    recommended = "stable"
```

This is recommendation-level policy logic, not automatic tuning yet.

Research directions:

- adaptive forgetting
- concept drift handling
- retention policy learning

## 5. Existing Asymmetries Worth Researching

These point to places where the current system is intentionally hybrid or still
partly heuristic.

### 5.1 UCB in one place, Thompson in another

- `engine/context.py` still uses UCB-like exploration for legacy skills
- `surface/knowledge_catalog.py` uses Thompson sampling for institutional memory

Research target:

- unified nonstationary bandit retrieval under delayed feedback

### 5.2 Rich posterior updates, but simpler trust penalties

- memory entries get quality-aware, decay-aware updates
- federated retrieval still uses coarse status-based penalties

Research target:

- trust-aware retrieval directly from peer posteriors or reputation models

### 5.3 Strong branching diagnostics, but heuristic topology priors

- stagnation detection uses entropy-like effective counts
- topology initialization from knowledge is still mostly domain-name overlap

Research target:

- principled mapping from long-term memory to communication graph priors

### 5.4 Strong confidence math, weaker contradiction math

- retrieval and confidence are statistically grounded
- contradiction resolution is still mostly heuristic arbitration

Research target:

- temporal belief revision
- conflicting evidence fusion
- competing-hypothesis maintenance

## 6. Highest-Value Research Topics

If you want to ask for one research paper or one paper cluster, these are the
best bets in priority order.

### 6.1 Nonstationary Thompson sampling and delayed bandits for decaying knowledge

Why this is first:

- directly touches retrieval ranking
- directly touches confidence updates
- directly touches delayed colony-outcome feedback
- could unify the old UCB path and the new Thompson path

Repo seams:

- `src/formicos/engine/context.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/colony_manager.py`

Questions:

- how should Thompson sampling behave when evidence decays?
- how should delayed task success feed back into retrieval posteriors?
- what is the correct update when the system is nonstationary by design?

### 6.2 ACO / MMAS / anti-stagnation control for multi-scale stigmergy

Why:

- best fit for the coordination + knowledge interaction
- directly relevant to pheromone update bounds, branching metrics, and topology
  priors

Repo seams:

- `src/formicos/engine/strategies/stigmergic.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/proactive_intelligence.py`

Questions:

- how should evaporation adapt when branching collapses?
- how should topology priors inherit long-term successful traces?
- how do you prevent premature convergence in a two-layer stigmergic system?

### 6.3 Budgeted context selection and diversity-aware packing

Why:

- the current context system is useful but heuristic
- there is room for a much more principled selection strategy

Repo seams:

- `src/formicos/engine/context.py`

Questions:

- what objective should context packing optimize?
- how should novelty and relevance be balanced under a hard token budget?
- should previous-round summaries, routed outputs, and knowledge compete in one
  optimizer instead of using fixed slices?

### 6.4 Reputation systems and trust-aware evidence fusion

Why:

- trust is already Bayesian, but not fully wired through retrieval and admission
- federation is a likely long-run differentiator

Repo seams:

- `src/formicos/surface/trust.py`
- `src/formicos/surface/admission.py`
- `src/formicos/core/crdt.py`
- `src/formicos/surface/federation.py`

Questions:

- how should peer trust influence retrieval beyond status bands?
- how should hop count and uncertainty interact?
- should foreign evidence update local posteriors directly or remain only a
  retrieval penalty?

### 6.5 Belief revision and contradiction resolution

Why:

- likely the least mature math in the current stack
- likely the biggest correctness win if improved

Repo seam:

- `src/formicos/surface/conflict_resolution.py`

Questions:

- when should the system keep competing hypotheses vs pick a winner?
- how should temporal recency be modeled?
- how should confidence mass, provenance, and source trust combine?

## 7. Useful Test Files To Read Before Research

These tests capture intended invariants better than the prose alone:

- `tests/unit/engine/test_ucb_scoring.py`
- `tests/unit/surface/test_scoring_invariants.py`
- `tests/unit/surface/test_cooccurrence_scoring.py`
- `tests/unit/surface/test_gamma_decay.py`
- `tests/unit/surface/test_bayesian_confidence.py`
- `tests/unit/surface/test_mastery_restoration.py`
- `tests/unit/surface/test_wave37_branching.py`
- `tests/unit/surface/test_wave38_federation_trust.py`
- `tests/unit/surface/test_parallel_planning.py`

## 8. Suggested Next Prompt For A Paper Hunt

If you want the cleanest single prompt to drive external research, use one of
these.

### Option A: retrieval / knowledge focus

`Find the best 2024-2026 papers on nonstationary Thompson sampling, discounted or sliding-window bandits, and delayed-reward retrieval systems that would apply to a shared decaying knowledge base with Beta posteriors. Prioritize papers that discuss nonstationarity, delayed feedback, exploration under uncertainty, and practical update rules.`

### Option B: coordination focus

`Find the best 2024-2026 papers on dynamic communication topology, ACO/MMAS anti-stagnation control, and multi-agent stigmergic coordination that can inform a two-layer system with short-term pheromone routing and long-term shared knowledge traces.`

### Option C: context focus

`Find the best 2024-2026 papers on submodular or diversity-aware context selection, budgeted retrieval, and query-focused summarization for LLM agents operating under strict token budgets.`

## 9. Final Take

The strongest research target in this codebase is not "memory" in the generic
sense. It is the mathematical coupling between:

- stochastic knowledge retrieval
- delayed outcome-based reinforcement
- decay and forgetting
- topology adaptation

That is where FormicOS is already unusually interesting, and that is where a
good paper is most likely to change the code in a meaningful way.
