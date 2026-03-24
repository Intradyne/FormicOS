# Phase 2 Algorithm & Contract Reference

**Purpose:** Consolidation of all algorithm details, event definitions, and scope criteria needed to complete Phase 2 deliverables. Extracted from Builder's Companion, Wave 3 Implementation Research, Scope Contract, and Architecture Reference. This is the orchestrator's working document — not a project artifact.

---

## 1. Event Payload Definitions (Builder's Companion §2.2)

### 1.1 Event Envelope

Every event shares:
- `seq: int` — monotonic, assigned by store
- `type: str` — discriminant matching the event class name
- `timestamp: datetime`
- `address: str` — serialized NodeAddress (e.g. `"ws-refactor/th-main/col-a1b2"`)
- `trace_id: str | None` — OTel correlation

### 1.2 Complete Alpha Event Types (~22)

**IMPORTANT SERIALIZATION NOTE:** The Clean-Slate Architecture Reference (which is authoritative) mandates **Pydantic v2 exclusively** with `frozen=True` and discriminated unions via `Annotated[Union[...], Field(discriminator='type')]`. The Builder's Companion was written earlier and references msgspec — **ignore all msgspec references**. Use Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True)`.

**Tree lifecycle:**

| Event | Payload Fields |
|-------|---------------|
| `WorkspaceCreated` | `name: str`, `config: dict` (model overrides, budget, strategy) |
| `ThreadCreated` | `workspace_id: str`, `name: str` |
| `ColonySpawned` | `thread_id: str`, `task: str`, `caste_names: list[str]`, `model_assignments: dict[str, str]`, `strategy: str`, `max_rounds: int`, `budget_limit: float` |
| `ColonyCompleted` | `colony_id: str`, `summary: str`, `skills_extracted: int` |
| `ColonyFailed` | `colony_id: str`, `reason: str` |
| `ColonyKilled` | `colony_id: str`, `killed_by: str` (operator or governance) |

**Round execution:**

| Event | Payload Fields |
|-------|---------------|
| `RoundStarted` | `colony_id: str`, `round_number: int` |
| `PhaseEntered` | `colony_id: str`, `round_number: int`, `phase: str` (goal, intent, route, execute, compress) |
| `AgentTurnStarted` | `colony_id: str`, `round_number: int`, `agent_id: str`, `caste: str`, `model: str` |
| `AgentTurnCompleted` | `agent_id: str`, `output_summary: str`, `input_tokens: int`, `output_tokens: int`, `tool_calls: list[str]`, `duration_ms: int` |
| `RoundCompleted` | `colony_id: str`, `round_number: int`, `convergence: float`, `cost: float`, `duration_ms: int` |

**Information flow (S2):**

| Event | Payload Fields |
|-------|---------------|
| `MergeCreated` | `edge_id: str`, `from_colony: str`, `to_colony: str`, `created_by: str` |
| `MergePruned` | `edge_id: str`, `pruned_by: str` |

**Context:**

| Event | Payload Fields |
|-------|---------------|
| `ContextUpdated` | `address: str`, `key: str`, `value: str`, `operation: str` (set or delete) |

**Configuration:**

| Event | Payload Fields |
|-------|---------------|
| `WorkspaceConfigChanged` | `workspace_id: str`, `field: str`, `old_value: str | None`, `new_value: str | None` |
| `ModelRegistered` | `provider_prefix: str`, `model_name: str`, `context_window: int`, `supports_tools: bool` |
| `ModelAssignmentChanged` | `scope: str` (system or workspace_id), `caste: str`, `old_model: str | None`, `new_model: str | None` |

**Governance:**

| Event | Payload Fields |
|-------|---------------|
| `ApprovalRequested` | `request_id: str`, `approval_type: str`, `detail: str`, `colony_id: str` |
| `ApprovalGranted` | `request_id: str` |
| `ApprovalDenied` | `request_id: str` |

**Queen:**

| Event | Payload Fields |
|-------|---------------|
| `QueenMessage` | `thread_id: str`, `role: str` (operator or queen), `content: str` |

**Observability:**

| Event | Payload Fields |
|-------|---------------|
| `TokensConsumed` | `agent_id: str`, `model: str`, `input_tokens: int`, `output_tokens: int`, `cost: float` |

That is 22 event types. The discriminated union is their sum type.

---

## 2. DyTopo Routing Algorithm (Wave 3 Research §1.2)

### 2.1 Adjacency Matrix Construction (per round)

```
INPUT:
  agents: List[Agent]
  round_goal: str
  tau: float = 0.35
  k_in: int = 3
  pheromone_weights: Dict[(i,j), float]

PHASE 2 — Descriptor generation (each agent, local model):
  for agent in agents:
    prompt = f"""
    Round goal: {round_goal}
    Your role: {agent.caste_description}
    Your current state: {agent.last_output_summary}
    
    Emit two short descriptors (1-2 sentences each):
    QUERY (what I need from others): ...
    KEY (what I can offer others): ...
    """
    agent.query, agent.key = parse_descriptors(llm_call(prompt))

PHASE 3 — Routing:
  # 1. Batch embed all descriptors
  all_texts = [a.query for a in agents] + [a.key for a in agents]
  embeddings = embed_batch(all_texts)  # snowflake-arctic-embed-s (384-dim)
  query_vecs = embeddings[:len(agents)]
  key_vecs = embeddings[len(agents):]
  
  # 2. Cosine similarity matrix (query_i x key_j for i != j)
  sim_matrix = cosine_similarity(query_vecs, key_vecs)
  
  # 3. Apply pheromone weighting BEFORE thresholding
  for (i, j) in pheromone_weights:
    sim_matrix[i][j] *= pheromone_weights[(i, j)]
  
  # 4. Zero diagonal (no self-edges)
  for i in range(len(agents)):
    sim_matrix[i][i] = 0.0
  
  # 5. Hard threshold
  adjacency = (sim_matrix >= tau).astype(int)
  
  # 6. Cap inbound edges per agent
  for j in range(len(agents)):
    inbound = [(sim_matrix[i][j], i) for i in range(len(agents)) if adjacency[i][j]]
    if len(inbound) > k_in:
      inbound.sort(reverse=True)
      keep = {i for _, i in inbound[:k_in]}
      for i in range(len(agents)):
        if i not in keep:
          adjacency[i][j] = 0
  
  # 7. Topological sort (break cycles by removing lowest-weight edge)
  exec_order = topological_sort(adjacency, root=manager_index)

OUTPUT:
  adjacency: NxN binary matrix
  exec_order: List[int]
  sim_matrix: NxN float
```

**Critical detail:** Pheromone weight is a multiplier on similarity BEFORE thresholding. A strong pheromone (1.8) can push marginal similarity (0.22) above tau (0.22 x 1.8 = 0.396 > 0.35). A decayed weight (0.15) can suppress moderate similarity (0.40 x 0.15 = 0.06 < 0.35). This is intentional.

### 2.2 Synchronization Barrier

All descriptors must be embedded and the adjacency matrix constructed before ANY agent begins Phase 4 execution. The barrier is implicit in sequential phase execution — do not break it.

---

## 3. Pheromone Update (Builder's Companion §14.3 + Wave 3 §2.2-2.3)

### 3.1 TopologyJanitor (additive approach)

```python
class TopologyJanitor:
    rho = 0.1       # evaporation rate
    alpha = 0.2     # learning rate
    w_min = 0.1
    w_max = 2.0
    weights: Dict[Tuple[str, str], float] = {}
    
    def update(self, adjacency, agents, round_outcome):
        for key in self.weights:
            self.weights[key] *= (1 - self.rho)
        for i, agent_i in enumerate(agents):
            for j, agent_j in enumerate(agents):
                if adjacency[i][j] == 1:
                    key = (agent_i.id, agent_j.id)
                    reward = self._compute_reward(round_outcome)
                    self.weights.setdefault(key, 1.0)
                    self.weights[key] += self.alpha * reward
        for key in self.weights:
            self.weights[key] = max(self.w_min, min(self.w_max, self.weights[key]))
```

### 3.2 Multiplicative approach (simpler, recommended for alpha)

```python
STRENGTHEN = 1.15
WEAKEN = 0.75
EVAPORATE = 0.95
BOUNDS = (0.1, 2.0)

for (a, b), weight in colony.pheromone_weights.items():
    new_weight = 1.0 + (weight - 1.0) * EVAPORATE
    if governance.action == "continue" and convergence_delta > 0:
        new_weight *= STRENGTHEN
    elif governance.action in ("halt", "warn"):
        new_weight *= WEAKEN
    colony.pheromone_weights[(a, b)] = clamp(new_weight, *BOUNDS)
```

### 3.3 Persistence

Serialize via `{f"{k[0]}:{k[1]}": v for k, v in weights.items()}`. Include in round checkpoint.

---

## 4. Context Assembly & Token Budgeting (Builder's Companion §7.3 + §14.2)

### 4.1 Context Assembly (Priority Order)

```python
async def assemble_context(agent_id, colony, topology, goal) -> list[dict]:
    messages = []
    budget = colony.config.context_budget_tokens  # default 4000

    # 1. System prompt (caste recipe) — always included, NOT counted against budget
    messages.append({"role": "system", "content": agent_recipe(agent_id).system_prompt})

    # 2. Goal for this round
    messages.append({"role": "user", "content": f"Round goal: {goal}"})

    # 3. Routed context — outputs from agents earlier in execution order
    for edge in topology.incoming_edges(agent_id):
        source_output = current_round_outputs.get(edge.from_agent)
        if source_output:
            messages.append({"role": "user", "content": f"[{edge.from_agent}]: {source_output}"})

    # 4. Merged context — from other colonies via merge edges
    active_merges = merge_view.edges_to(colony.id)
    for merge in active_merges:
        source_summary = await get_colony_compressed_output(merge.from_colony)
        if source_summary:
            messages.append({"role": "user", "content": f"[Merged from {merge.from_colony}]: {source_summary}"})

    # 5. Previous round compressed summary
    if colony.prev_round_summary:
        messages.append({"role": "user", "content": f"Previous round: {colony.prev_round_summary}"})

    # 6. Skill bank — retrieve relevant skills
    skills = await vector_port.search(namespace=colony.workspace_id, query=goal, top_k=3)
    if skills:
        skill_text = "\n".join(s.content for s in skills)
        messages.append({"role": "user", "content": f"Relevant skills:\n{skill_text}"})

    return trim_to_budget(messages, budget)
```

### 4.2 Token Budget Trimming

```python
def trim_to_budget(messages, budget_tokens):
    total = sum(estimate_tokens(m["content"]) for m in messages)
    if total <= budget_tokens:
        return messages
    result = list(messages)
    while total > budget_tokens and len(result) > 1:
        removed = result.pop()
        total -= estimate_tokens(removed["content"])
    return result

def estimate_tokens(text):
    return len(text) // 4
```

---

## 5. Convergence & Stall Detection (Wave 3 Research §3.2-3.3)

### 5.1 Convergence Score

```python
def compute_convergence_score(prev_summary_vec, curr_summary_vec, goal_vec, round_num, max_rounds):
    goal_alignment = cosine_similarity(curr_summary_vec, goal_vec)
    stability = cosine_similarity(prev_summary_vec, curr_summary_vec) if prev_summary_vec is not None else 0.0
    if prev_summary_vec is not None:
        prev_alignment = cosine_similarity(prev_summary_vec, goal_vec)
        progress = max(0, goal_alignment - prev_alignment)
    else:
        progress = goal_alignment
    score = 0.4 * goal_alignment + 0.3 * stability + 0.3 * min(1.0, progress * 5)
    return ConvergenceResult(
        score=score, goal_alignment=goal_alignment, stability=stability, progress=progress,
        is_stalled=(stability > 0.95 and progress < 0.01 and round_num > 2),
        is_converged=(score > 0.85 and stability > 0.90),
    )
```

### 5.2 Stall Detection Triggers

| Condition | Consecutive Rounds | Action |
|-----------|-------------------|--------|
| `stability > 0.95 AND progress < 0.01` | 2 | `warn_tunnel_vision` |
| `stability > 0.95 AND progress < 0.01` | 4 | `force_halt` |
| `goal_alignment < 0.2` | after round 3 | `warn_off_track` |
| `score > 0.85 AND stability > 0.90` | 2 | `suggest_early_stop` |

### 5.3 Path Diversity

```python
def compute_path_diversity(round_outputs, embedding_model):
    if len(round_outputs) < 2:
        return 0.0
    vecs = embedding_model.encode(round_outputs, normalize_embeddings=True)
    n = len(vecs)
    total_distance = sum(1 - np.dot(vecs[i], vecs[j]) for i in range(n) for j in range(i+1, n))
    pairs = n * (n - 1) / 2
    return min(1.0, total_distance / pairs)
```

If `path_diversity < 0.15` for 2+ consecutive rounds AND not converged: `warn_tunnel_vision`.

---

## 6. LLM Adapter Patterns (Builder's Companion §6.1 + Implementation Plan Stream C)

### 6.1 Port Interface

Uses `typing.Protocol` per ADR-004. No ABC.

```python
class LLMPort(Protocol):
    async def complete(self, model: str, messages: list[dict],
                       tools: list[dict] | None = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> LLMResponse: ...
    async def stream(self, model: str, messages: list[dict],
                     tools: list[dict] | None = None,
                     temperature: float = 0.0, max_tokens: int = 4096) -> AsyncIterator[LLMChunk]: ...
```

### 6.2 Provider-Prefix Routing

`model.split("/")[0]` maps to adapter. Router in surface/, not engine/.

### 6.3 Anthropic Adapter (~200 LOC)

httpx.AsyncClient, POST to api.anthropic.com/v1/messages, SSE streaming, tool_use content blocks, retry 429/529 with backoff.

### 6.4 OpenAI-Compatible Adapter (~200 LOC)

Configurable base_url, OpenAI function-calling format, no API key for local models.

### 6.5 Response Types (frozen Pydantic)

```python
class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    tool_calls: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str

class LLMChunk(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    is_final: bool
```

---

## 7. Scope Contract S1-S9 (complete acceptance criteria)

### S1: Tree renders and navigates
Tree shows Workspace > Thread > Colony. Breadcrumb. Sidebar collapses to icon rail.

### S2: Merge, prune, broadcast
Thread view shows merge edges. Connect/prune/broadcast controls. Events emitted. Merged context visible.

### S3: Workspaces are configuration containers
Config + Threads sections. Model overrides per caste. Budget. Null = inherit.

### S4: Queen multi-chat threads
Tabbed conversations. Operator + Queen + inline events. Persist across sessions.

### S5: Model registry and assignment
Local + cloud models. Workspace overrides. Cascade visible.

### S6: Thread is operational workspace
Queen chat + colony graph + merge edges. Spawn from here.

### S7: External MCP orchestration
spawn_colony, get_status, query_memory, list_workspaces, chat_queen. Workspace-scoped.

### S8: Event-sourced persistence
Single SQLite. Stop/restart preserves state. No duplicate DBs.

### S9: Startup
docker compose up. First-run model setup. Works with local only.

### Non-goals
PTC sandbox, Queen-composed dashboards, federation, experiment engine, research colony, SkillRL, H-Neuron, A2A beyond discovery, RBAC, MCP Apps, compute router, automated cost routing.

### Priority: S2 > S4 > S6 > S3 > S5 > rest

---

## 8. Event Store Schema

```sql
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL, timestamp TEXT NOT NULL,
    address TEXT NOT NULL, payload TEXT NOT NULL, trace_id TEXT
);
CREATE INDEX idx_events_address ON events(address, seq);
CREATE INDEX idx_events_type ON events(type, seq);
CREATE INDEX idx_events_trace ON events(trace_id) WHERE trace_id IS NOT NULL;
```

Views: active merge edges, colony status, token accounting, workspace configs. Each has rebuild_from(events) + apply(event).

---

## 9. Experimentable Parameters

| Param | Default | Range |
|-------|---------|-------|
| tau | 0.35 | [0.2, 0.6] |
| k_in | 3 | [1, N-1] |
| rho | 0.1 | [0.01, 0.5] |
| alpha | 0.2 | [0.05, 0.5] |
| w_min/w_max | 0.1/2.0 | configurable |
| convergence_weights | [0.4,0.3,0.3] | simplex |
| stall_rounds_warn | 2 | [1,4] |
| stall_rounds_halt | 4 | [2,8] |
| diversity_threshold | 0.15 | [0.05,0.3] |
| context_budget_tokens | 4000 | [2000,8000] |

---

## 10. types.ts Fixes

1. Add GovernanceConfig, RoutingConfig, EmbeddingConfig. Add queen to defaults.
2. Replace generic payload bag with discriminated event union matching 22 Python types.
3. Standardize: traceId (TS camelCase), trace_id (Python snake_case). WS layer transforms.
4. Replace generic WS payloads with action-specific command union.
