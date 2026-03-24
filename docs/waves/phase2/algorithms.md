# Phase 2 Algorithms

## Purpose
This document freezes the alpha algorithms that implement FormicOS coordination,
context flow, convergence checks, and model resolution. Runtime code in Phase 3
must implement these procedures without changing field names or event semantics.

## Runtime parameter source
- Thresholds and defaults come from configuration when present.
- The pseudocode below shows the canonical algorithm shape.
- Null overrides always mean "inherit from the parent scope."

## 1. Colony round execution

```python
async def run_round(colony, round_number, services):
    round_started_at = now_ms()
    emit(RoundStarted(..., colony_id=colony.id, round_number=round_number))

    emit(PhaseEntered(..., colony_id=colony.id, round_number=round_number, phase="goal"))
    round_goal = derive_round_goal(colony=colony, round_number=round_number)

    emit(PhaseEntered(..., colony_id=colony.id, round_number=round_number, phase="intent"))
    descriptors = await generate_descriptors(
        agents=colony.agents,
        round_goal=round_goal,
        llm_port=services.llm_port,
    )

    emit(PhaseEntered(..., colony_id=colony.id, round_number=round_number, phase="route"))
    routing = await resolve_adjacency_and_order(
        agents=colony.agents,
        round_goal=round_goal,
        descriptors=descriptors,
        pheromone_weights=colony.pheromone_weights,
        tau=colony.routing.tau_threshold,
        k_in=colony.routing.k_in_cap,
        embedder=services.embedding_model,
    )

    emit(PhaseEntered(..., colony_id=colony.id, round_number=round_number, phase="execute"))
    current_round_outputs = {}
    current_round_cost = 0.0
    for execution_group in routing.execution_groups:
        group_results = await execute_group(
            colony=colony,
            round_number=round_number,
            agent_ids=execution_group,
            round_goal=round_goal,
            routing=routing,
            current_round_outputs=current_round_outputs,
            services=services,
        )
        current_round_outputs.update(group_results.outputs)
        current_round_cost += group_results.cost

    emit(PhaseEntered(..., colony_id=colony.id, round_number=round_number, phase="compress"))
    round_summary = compress_round_outputs(
        current_round_outputs=current_round_outputs,
        previous_summary=colony.prev_round_summary,
    )
    convergence = compute_convergence_result(
        prev_summary=colony.prev_round_summary,
        curr_summary=round_summary,
        goal=round_goal,
        round_num=round_number,
        max_rounds=colony.max_rounds,
        embedding_model=services.embedding_model,
    )
    governance = evaluate_governance(
        convergence=convergence,
        path_diversity=compute_path_diversity(list(current_round_outputs.values()), services.embedding_model),
        round_number=round_number,
    )
    colony.pheromone_weights = update_pheromone_weights(
        weights=colony.pheromone_weights,
        active_edges=routing.active_edges,
        governance_action=governance.action,
        convergence_delta=convergence.progress,
    )

    emit(
        RoundCompleted(
            ...,
            colony_id=colony.id,
            round_number=round_number,
            convergence=convergence.score,
            cost=current_round_cost,
            duration_ms=now_ms() - round_started_at,
        )
    )

    skills_extracted = extract_skills(round_summary)

    if governance.action in ("force_halt", "halt"):
        emit(ColonyFailed(..., colony_id=colony.id, reason=governance.reason))
    elif governance.action == "complete" or round_number >= colony.max_rounds:
        emit(
            ColonyCompleted(
                ...,
                colony_id=colony.id,
                summary=round_summary,
                skills_extracted=skills_extracted,
            )
        )
    else:
        colony.prev_round_summary = round_summary
        checkpoint(colony)
```

### Notes
- The evented phase names are `goal`, `intent`, `route`, `execute`, and `compress`.
- Governance decisions happen after compression and before the next round is scheduled.
- Descriptor generation, routing, and execution must remain barriered phase steps.

## 2. Adjacency matrix construction

```python
async def resolve_adjacency_and_order(agents, round_goal, descriptors, pheromone_weights, tau, k_in, embedder):
    all_texts = [d.query for d in descriptors] + [d.key for d in descriptors]
    embeddings = embedder.encode(all_texts, normalize_embeddings=True)
    query_vecs = embeddings[: len(agents)]
    key_vecs = embeddings[len(agents) :]

    sim_matrix = cosine_similarity(query_vecs, key_vecs)

    for (source_id, target_id), weight in pheromone_weights.items():
        i = agent_index(source_id, agents)
        j = agent_index(target_id, agents)
        if i is not None and j is not None:
            sim_matrix[i][j] *= weight

    for i in range(len(agents)):
        sim_matrix[i][i] = 0.0

    adjacency = (sim_matrix >= tau).astype(int)

    for j in range(len(agents)):
        inbound = [(sim_matrix[i][j], i) for i in range(len(agents)) if adjacency[i][j] == 1]
        if len(inbound) > k_in:
            inbound.sort(reverse=True)
            keep = {i for _, i in inbound[:k_in]}
            for i in range(len(agents)):
                if adjacency[i][j] == 1 and i not in keep:
                    adjacency[i][j] = 0

    adjacency = break_cycles_by_lowest_weight_edge(adjacency, sim_matrix)
    execution_order = topological_sort(adjacency, root=manager_index(agents))
    execution_groups = collapse_into_parallel_layers(adjacency, execution_order)

    return RoutingResult(
        adjacency=adjacency,
        similarity_matrix=sim_matrix,
        execution_order=execution_order,
        execution_groups=execution_groups,
        active_edges=materialize_edges(adjacency, agents),
    )
```

### Critical details
- Pheromone weights multiply cosine similarity before thresholding.
- `k_in` caps inbound edges per destination agent after thresholding.
- No agent may route to itself.
- No execution may begin before the full descriptor set is embedded and routed.

## 3. Descriptor generation

```python
async def generate_descriptors(agents, round_goal, llm_port):
    descriptors = []
    for agent in agents:
        prompt = f"""
        Round goal: {round_goal}
        Your role: {agent.caste_description}
        Your current state: {agent.last_output_summary}

        Emit two short descriptors (1-2 sentences each):
        QUERY (what I need from others): ...
        KEY (what I can offer others): ...
        """
        result = await llm_port.complete(model=agent.model, messages=[{"role": "user", "content": prompt}])
        descriptors.append(parse_descriptors(result.content))
    return descriptors
```

## 4. Group execution and context assembly

```python
async def execute_group(colony, round_number, agent_ids, round_goal, routing, current_round_outputs, services):
    async def run_agent(agent_id):
        agent = colony.agent_by_id(agent_id)
        turn_started_at = now_ms()
        emit(
            AgentTurnStarted(
                ...,
                colony_id=colony.id,
                round_number=round_number,
                agent_id=agent.id,
                caste=agent.caste,
                model=agent.model,
            )
        )
        messages = await assemble_context(
            agent_id=agent.id,
            colony=colony,
            routing=routing,
            round_goal=round_goal,
            current_round_outputs=current_round_outputs,
            vector_port=services.vector_port,
            archive=services.archive,
        )
        response = await services.llm_port.complete(
            model=agent.model,
            messages=messages,
            tools=agent.tools,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )
        duration_ms = now_ms() - turn_started_at
        cost = estimate_cost(
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            registry=services.model_registry,
        )
        emit(
            AgentTurnCompleted(
                ...,
                agent_id=agent.id,
                output_summary=summarize(response.content),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                tool_calls=[call["name"] for call in response.tool_calls],
                duration_ms=duration_ms,
            )
        )
        emit(
            TokensConsumed(
                ...,
                agent_id=agent.id,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost=cost,
            )
        )
        return agent.id, response.content, cost

    results = await gather_preserving_input(agent_ids, run_agent)
    return GroupExecutionResult.from_results(results)
```

```python
async def assemble_context(agent_id, colony, routing, round_goal, current_round_outputs, vector_port, archive):
    messages = []
    budget = colony.context_budget_tokens or 4000

    messages.append({"role": "system", "content": colony.recipe_for(agent_id).system_prompt})
    messages.append({"role": "user", "content": f"Round goal: {round_goal}"})

    for edge in routing.incoming_edges(agent_id):
        source_output = current_round_outputs.get(edge.from_agent)
        if source_output:
            messages.append({"role": "user", "content": f"[{edge.from_agent}]: {source_output}"})

    for merged_message in resolve_merged_context(colony, archive):
        messages.append({"role": "user", "content": merged_message})

    if colony.prev_round_summary:
        messages.append({"role": "user", "content": f"Previous round: {colony.prev_round_summary}"})

    skills = await vector_port.search(collection=colony.workspace_id, query=round_goal, top_k=3)
    if skills:
        skill_text = "\n".join(skill.content for skill in skills)
        messages.append({"role": "user", "content": f"Relevant skills:\n{skill_text}"})

    return trim_to_budget(messages, budget)
```

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

### Context priority order
1. System prompt from the caste recipe, not counted against budget
2. Round goal
3. Routed context from earlier agents in the current execution order
4. Merged context from inbound active merge edges
5. Previous round compressed summary
6. Retrieved skills from vector memory

## 5. Merge resolution

```python
def resolve_merged_context(colony, archive):
    merged_messages = []
    inbound_edges = sort_inbound_merges(colony.active_inbound_merges)
    for edge in inbound_edges:
        source_summary = archive.get_colony_compressed_output(edge.from_colony)
        if source_summary:
            merged_messages.append(f"[Merged from {edge.from_colony}]: {source_summary}")
    return merged_messages
```

### Rules
- Only active inbound merge edges are considered.
- Merge resolution operates on compressed colony output, never raw round transcripts.
- Merge messages are inserted after routed intra-colony context and before previous-round summary.

## 6. Pheromone update

```python
def update_pheromone_weights(weights, active_edges, governance_action, convergence_delta):
    updated = dict(weights)
    strengthen = 1.15
    weaken = 0.75
    evaporate = 0.95
    lower, upper = (0.1, 2.0)

    for edge_key, weight in updated.items():
        updated[edge_key] = 1.0 + (weight - 1.0) * evaporate

    for edge in active_edges:
        key = (edge.from_agent, edge.to_agent)
        current = updated.get(key, 1.0)
        if governance_action == "continue" and convergence_delta > 0:
            current *= strengthen
        elif governance_action in ("halt", "force_halt", "warn"):
            current *= weaken
        updated[key] = clamp(current, lower, upper)

    return updated
```

### Persistence format

```python
def serialize_pheromone_weights(weights):
    return {f"{source}:{target}": value for (source, target), value in weights.items()}
```

## 7. Convergence detection

```python
def compute_convergence_result(prev_summary, curr_summary, goal, round_num, max_rounds, embedding_model):
    goal_vec = embedding_model.encode([goal], normalize_embeddings=True)[0]
    curr_vec = embedding_model.encode([curr_summary], normalize_embeddings=True)[0]
    prev_vec = None
    if prev_summary is not None:
        prev_vec = embedding_model.encode([prev_summary], normalize_embeddings=True)[0]

    goal_alignment = cosine_similarity(curr_vec, goal_vec)
    stability = cosine_similarity(prev_vec, curr_vec) if prev_vec is not None else 0.0

    if prev_vec is not None:
        prev_alignment = cosine_similarity(prev_vec, goal_vec)
        progress = max(0.0, goal_alignment - prev_alignment)
    else:
        progress = goal_alignment

    score = 0.4 * goal_alignment + 0.3 * stability + 0.3 * min(1.0, progress * 5.0)
    return ConvergenceResult(
        score=score,
        goal_alignment=goal_alignment,
        stability=stability,
        progress=progress,
        is_stalled=(stability > 0.95 and progress < 0.01 and round_num > 2),
        is_converged=(score > 0.85 and stability > 0.90),
        max_rounds=max_rounds,
    )
```

## 8. Stall detection and governance actions

```python
def evaluate_governance(convergence, path_diversity, round_number):
    if convergence.stability > 0.95 and convergence.progress < 0.01 and round_number >= 4:
        return GovernanceDecision(action="force_halt", reason="stalled_four_rounds")
    if convergence.stability > 0.95 and convergence.progress < 0.01 and round_number >= 2:
        return GovernanceDecision(action="warn", reason="warn_tunnel_vision")
    if convergence.goal_alignment < 0.2 and round_number > 3:
        return GovernanceDecision(action="warn", reason="warn_off_track")
    if convergence.is_converged and round_number >= 2:
        return GovernanceDecision(action="complete", reason="suggest_early_stop")
    if path_diversity < 0.15 and round_number >= 2 and not convergence.is_converged:
        return GovernanceDecision(action="warn", reason="warn_low_path_diversity")
    return GovernanceDecision(action="continue", reason="continue")
```

### Trigger table
| Condition | Consecutive rounds | Action |
|---|---:|---|
| `stability > 0.95` and `progress < 0.01` | 2 | `warn_tunnel_vision` |
| `stability > 0.95` and `progress < 0.01` | 4 | `force_halt` |
| `goal_alignment < 0.2` after round 3 | 1 | `warn_off_track` |
| `score > 0.85` and `stability > 0.90` | 2 | `suggest_early_stop` |
| `path_diversity < 0.15` and not converged | 2 | `warn_tunnel_vision` |

## 9. Path diversity

```python
def compute_path_diversity(round_outputs, embedding_model):
    if len(round_outputs) < 2:
        return 0.0

    vecs = embedding_model.encode(round_outputs, normalize_embeddings=True)
    n = len(vecs)
    total_distance = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            total_distance += 1.0 - dot(vecs[i], vecs[j])

    pairs = n * (n - 1) / 2
    return min(1.0, total_distance / pairs)
```

## 10. Model cascade resolution

```python
def resolve_model_for_caste(caste, thread_config, workspace_config, system_defaults):
    thread_value = thread_config.get(f"{caste}_model")
    if thread_value is not None:
        return thread_value

    workspace_value = workspace_config.get(f"{caste}_model")
    if workspace_value is not None:
        return workspace_value

    return system_defaults[caste]
```

### Rules
- Resolution order is thread -> workspace -> system.
- Null means inherit from the next parent scope.
- Resolved assignments are frozen into `ColonySpawned.model_assignments`.

## 11. External model adapter routing

```python
def route_model_to_adapter(model_address, adapters):
    provider_prefix = model_address.split("/", 1)[0]
    return adapters[provider_prefix]
```

### Rules
- Provider-prefix routing lives in surface or adapter wiring, never in engine.
- Anthropic uses direct Messages API translation.
- OpenAI-compatible adapters use configurable base URLs and function-calling translation.

## 12. Event store record shape

```sql
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    address TEXT NOT NULL,
    payload TEXT NOT NULL,
    trace_id TEXT
);
```

### Indexes
- `idx_events_address(address, seq)`
- `idx_events_type(type, seq)`
- `idx_events_trace(trace_id)` when `trace_id IS NOT NULL`
