# Wave 8 Algorithm Reference

## Purpose

This document provides the implementation algorithms for Wave 8 ("Close the Loop").
Coders implement these procedures. If an algorithm here contradicts an ADR, the
ADR wins. If an algorithm here contradicts `docs/contracts/`, the contract wins.

Reference ADRs: 007 (agent tools), 008 (context management), 009 (cost tracking),
010 (skill crystallization), 011 (quality scoring).

---

## 1. Agent Tool Execution Loop (ADR-007)

### 1.1 Tool Spec Construction

Build tool specs from the agent's recipe at the start of each agent turn.
Only build specs for tools with registered handlers.

```python
# In runner.py — new module-level registry

_TOOL_HANDLERS: dict[str, Callable] = {}
# Populated by _register_tools() at RoundRunner construction

TOOL_SPECS: dict[str, LLMToolSpec] = {
    "memory_search": {
        "name": "memory_search",
        "description": "Search the colony skill bank and workspace memory for relevant knowledge. Returns up to top_k results ranked by semantic similarity.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum results to return (1-10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    "memory_write": {
        "name": "memory_write",
        "description": "Store a piece of knowledge in the workspace memory for future retrieval by any agent. Use for findings, decisions, and reusable patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The knowledge to store. Be specific and self-contained.",
                },
                "metadata_type": {
                    "type": "string",
                    "description": "Category: finding, decision, pattern, or note",
                    "enum": ["finding", "decision", "pattern", "note"],
                },
            },
            "required": ["content"],
        },
    },
}
```

### 1.2 Tool Handler Implementations

```python
async def _handle_memory_search(
    vector_port: VectorPort,
    workspace_id: str,
    arguments: dict,
) -> str:
    """Execute memory_search tool call. Returns formatted results."""
    query = arguments.get("query", "")
    top_k = min(arguments.get("top_k", 5), 10)  # cap at 10

    if not query:
        return "Error: query is required"

    # Search both the global skill bank and workspace-scoped collection
    results: list[VectorSearchHit] = []
    for collection in ["skill_bank", workspace_id]:
        try:
            hits = await vector_port.search(
                collection=collection,
                query=query,
                top_k=top_k,
            )
            results.extend(hits)
        except Exception:
            pass  # collection may not exist yet — not an error

    if not results:
        return "No results found."

    # Deduplicate by id (same doc may appear in both collections)
    seen: set[str] = set()
    unique: list[VectorSearchHit] = []
    for hit in results:
        if hit.id not in seen:
            seen.add(hit.id)
            unique.append(hit)

    # Sort by score (lower distance = better for LanceDB), take top_k
    unique.sort(key=lambda h: h.score)
    unique = unique[:top_k]

    # Format for LLM consumption
    parts = []
    for i, hit in enumerate(unique, 1):
        parts.append(f"[{i}] {hit.content[:500]}")
    return "\n\n".join(parts)


async def _handle_memory_write(
    vector_port: VectorPort,
    workspace_id: str,
    colony_id: str,
    agent_id: str,
    arguments: dict,
) -> str:
    """Execute memory_write tool call. Returns confirmation."""
    content = arguments.get("content", "")
    if not content:
        return "Error: content is required"

    meta_type = arguments.get("metadata_type", "note")

    doc = VectorDocument(
        id=f"mem-{colony_id}-{agent_id}-{uuid4().hex[:8]}",
        content=content[:2000],  # cap content length
        metadata={
            "type": meta_type,
            "source_colony_id": colony_id,
            "source_agent_id": agent_id,
            "workspace_id": workspace_id,
        },
    )
    count = await vector_port.upsert(collection=workspace_id, docs=[doc])
    return f"Stored {count} document(s) in workspace memory."
```

### 1.3 The Tool Call Loop

Modified `_run_agent` in `runner.py`. The loop runs up to MAX_TOOL_ITERATIONS
rounds of tool calling before forcing a final text response.

```python
MAX_TOOL_ITERATIONS = 3
TOOL_OUTPUT_CAP = 2000  # chars per tool result

async def _run_agent(self, agent, colony_context, round_goal, ...):
    t0 = time.monotonic()
    # ... emit AgentTurnStarted (unchanged) ...

    messages = await assemble_context(...)  # unchanged

    # Build tool specs for this agent's declared tools
    available_tools: list[LLMToolSpec] = []
    for tool_name in agent.recipe.tools:
        if tool_name in TOOL_SPECS:
            available_tools.append(TOOL_SPECS[tool_name])
    # If no valid tools, pass None (same as current behavior)
    tools_arg = available_tools if available_tools else None

    # Tool call loop
    all_tool_names: list[str] = []
    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        is_final_iteration = (iteration == MAX_TOOL_ITERATIONS)

        response = await llm_port.complete(
            model=agent.model,
            messages=messages,
            tools=None if is_final_iteration else tools_arg,
            temperature=agent.recipe.temperature,
            max_tokens=agent.recipe.max_tokens,
        )

        # If no tool calls, we have a text response — done
        if not response.tool_calls:
            break

        # If this was the last allowed iteration, force text
        if is_final_iteration:
            break

        # Process tool calls
        for tc in response.tool_calls:
            tool_name = tc.get("name", "") or tc.get("function", {}).get("name", "")
            tool_args = _parse_tool_args(tc)
            all_tool_names.append(tool_name)

            result = await self._execute_tool(
                tool_name, tool_args,
                vector_port=vector_port,
                workspace_id=colony_context.workspace_id,
                colony_id=colony_context.colony_id,
                agent_id=agent.id,
            )

            # Truncate tool output
            if len(result) > TOOL_OUTPUT_CAP:
                result = result[:TOOL_OUTPUT_CAP] + "\n[... truncated]"

            # Append assistant message with tool calls + tool result.
            # IMPORTANT: keep tool feedback provider-neutral. The live
            # LLMMessage contract is still {role, content}, so do NOT use a
            # provider-native {"role": "tool"} message here.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": f"[Tool result: {tool_name}]\n{result}",
            })

    # ... rest of _run_agent (emit events, track cost) — unchanged
    # except: tool_calls list includes all_tool_names from the loop
```

### 1.4 Tool Argument Parsing

LLM providers format tool call arguments differently. Normalize:

```python
def _parse_tool_args(tc: dict) -> dict:
    """Extract arguments from either OpenAI or Anthropic tool call format."""
    # Anthropic format: {"name": "...", "input": {...}}
    if "input" in tc:
        return tc["input"]
    # OpenAI format: {"function": {"name": "...", "arguments": "{...}"}}
    args = tc.get("arguments", tc.get("function", {}).get("arguments", "{}"))
    if isinstance(args, str):
        import json
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return args
```

Note: `Runtime.parse_tool_input()` in `surface/runtime.py` already does this
for the Queen's tool calls. The runner needs its own copy because engine/
cannot import from surface/ (layer boundary). Duplicate the 8-line function
in `runner.py`. A shared utility is unnecessary for this wave.

---

## 2. Tiered Context Assembly (ADR-008)

### 2.1 Configuration Schema

Add to `formicos.yaml` under a new top-level `context` key:

```yaml
context:
  total_budget_tokens: 4000           # total non-system-prompt budget
  tier_budgets:
    goal: 500
    routed_outputs: 1500
    max_per_source: 500               # per-agent output cap within routed_outputs
    merge_summaries: 500
    prev_round_summary: 500
    skill_bank: 800
  compaction_threshold: 500           # compress prev_round_summary if over this
```

### 2.2 Revised assemble_context

```python
async def assemble_context(
    agent: AgentConfig,
    colony_context: ColonyContext,
    round_goal: str,
    routed_outputs: dict[str, str],
    merged_summaries: list[str],
    vector_port: VectorPort | None,
    tier_budgets: TierBudgets | None = None,  # NEW parameter
) -> list[LLMMessage]:
    """Build message list with per-tier budget enforcement.

    Assembly order (optimized for attention — important at edges):
      1. System prompt                 (position 1 — highest attention)
      2. Round goal                    (position 2 — task must be salient)
      3. Routed agent outputs          (middle — acceptable attention zone)
      4. Merge summaries               (middle)
      5. Previous round summary        (near end — decent recall)
      6. Skill bank results            (last — good recall, lowest trim priority)
    """
    budgets = tier_budgets or DEFAULT_TIER_BUDGETS
    messages: list[LLMMessage] = []

    # 1. System prompt (always present, not budget-limited)
    messages.append({"role": "system", "content": agent.recipe.system_prompt})

    # 2. Round goal (capped)
    goal_text = _truncate(f"Round goal: {round_goal}", budgets.goal)
    messages.append({"role": "user", "content": goal_text})

    # 3. Routed context with per-source cap
    routed_budget = budgets.routed_outputs
    routed_used = 0
    for source_id, output in routed_outputs.items():
        if routed_used >= routed_budget:
            break
        capped = _truncate_preserve_edges(output, budgets.max_per_source)
        msg_text = f"[{source_id}]: {capped}"
        msg_tokens = estimate_tokens(msg_text)
        if routed_used + msg_tokens > routed_budget:
            break
        messages.append({"role": "user", "content": msg_text})
        routed_used += msg_tokens

    # 4. Merge summaries (capped)
    merge_used = 0
    for summary in merged_summaries:
        if merge_used >= budgets.merge_summaries:
            break
        capped = _truncate(summary, budgets.merge_summaries - merge_used)
        messages.append({"role": "user", "content": capped})
        merge_used += estimate_tokens(capped)

    # 5. Previous round summary (compacted if over threshold)
    if colony_context.prev_round_summary:
        prev = colony_context.prev_round_summary
        if estimate_tokens(prev) > budgets.compaction_threshold:
            prev = _compact_summary(prev, round_goal, budgets.prev_round_summary)
        prev_text = _truncate(f"Previous round: {prev}", budgets.prev_round_summary)
        messages.append({"role": "user", "content": prev_text})

    # 6. Skill bank (best-effort, budget-capped)
    if vector_port is not None:
        try:
            skills = await vector_port.search(
                collection="skill_bank",
                query=round_goal,
                top_k=3,
            )
            if skills:
                skill_text = "\n".join(s.content[:300] for s in skills)
                skill_text = _truncate(
                    f"Relevant skills:\n{skill_text}",
                    budgets.skill_bank,
                )
                messages.append({"role": "user", "content": skill_text})
        except Exception:
            pass  # skill_bank collection may not exist yet

    return messages
```

### 2.3 Compaction Algorithm

Extractive compaction — no LLM call, pure Python, deterministic.

```python
def _compact_summary(
    text: str,
    goal: str,
    budget_tokens: int,
) -> str:
    """Compress text to budget by keeping goal-relevant sentences.

    Algorithm:
    1. Split into sentences (simple period/newline split).
    2. Score each sentence by keyword overlap with goal.
    3. Keep top-scoring sentences that fit within budget.
    4. Reassemble in original order to preserve coherence.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return text[:budget_tokens * 4]  # fallback to raw truncation

    goal_words = set(goal.lower().split())

    scored: list[tuple[int, float, str]] = []  # (original_index, score, text)
    for i, sent in enumerate(sentences):
        sent_words = set(sent.lower().split())
        overlap = len(goal_words & sent_words)
        # Bias toward first and last sentences (they carry structure)
        position_bonus = 0.5 if (i == 0 or i == len(sentences) - 1) else 0.0
        score = overlap + position_bonus
        scored.append((i, score, sent))

    # Sort by score descending, pick top-K within budget
    scored.sort(key=lambda x: -x[1])
    selected: list[tuple[int, str]] = []
    used_tokens = 0
    for idx, _score, sent in scored:
        sent_tokens = estimate_tokens(sent)
        if used_tokens + sent_tokens > budget_tokens:
            continue
        selected.append((idx, sent))
        used_tokens += sent_tokens

    # Reassemble in original order
    selected.sort(key=lambda x: x[0])
    return " ".join(s for _, s in selected)


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter. Not perfect, but fast and deterministic."""
    import re
    parts = re.split(r'(?<=[.!?\n])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]
```

### 2.4 Edge-Preserving Truncation

For routed agent outputs, preserve the first and last portions rather than
just chopping from the end. Opening paragraphs contain intent/summary; closing
paragraphs contain conclusions.

```python
def _truncate_preserve_edges(text: str, budget_tokens: int) -> str:
    """Truncate keeping first and last portions (edges have highest info density)."""
    text_tokens = estimate_tokens(text)
    if text_tokens <= budget_tokens:
        return text

    # Reserve half the budget for each edge
    char_budget = budget_tokens * 4  # rough token-to-char
    half = char_budget // 2
    return text[:half] + "\n[... truncated ...]\n" + text[-half:]
```

---

## 3. Cost Computation (ADR-009)

### 3.1 Cost Function Construction

In `surface/app.py`, build the cost function from the model registry:

```python
def _build_cost_fn(
    registry: list[ModelRecord],
) -> Callable[[str, int, int], float]:
    """Build a cost function that maps (model, input_tokens, output_tokens) -> USD."""
    rate_map: dict[str, tuple[float, float]] = {}
    for model in registry:
        input_rate = model.cost_per_input_token or 0.0
        output_rate = model.cost_per_output_token or 0.0
        rate_map[model.address] = (input_rate, output_rate)

    def cost_fn(model: str, input_tokens: int, output_tokens: int) -> float:
        rates = rate_map.get(model, (0.0, 0.0))
        return (input_tokens * rates[0]) + (output_tokens * rates[1])

    return cost_fn
```

### 3.2 Injection into RoundRunner

```python
# In RoundRunner.__init__
def __init__(
    self,
    emit: Callable[[FormicOSEvent], Any],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    cost_fn: Callable[[str, int, int], float] | None = None,  # NEW
) -> None:
    self._emit = emit
    self._embed_fn = embed_fn
    self._cost_fn = cost_fn or (lambda m, i, o: 0.0)

# In _run_agent, replace estimated_cost = 0.0:
estimated_cost = self._cost_fn(
    agent.model, response.input_tokens, response.output_tokens,
)
```

---

## 4. Skill Crystallization (ADR-010)

### 4.1 Post-Completion Extraction

**⚠ CRITICAL SEQUENCING: Crystallization runs BEFORE emitting `ColonyCompleted`,
not after.** The event is the source of truth (ADR-001). `ColonyCompleted` carries
`skills_extracted: int` — that field must contain the real count at emission time.
If you crystallize after the event, the event permanently records `0` and replay
will never see the correct count. The current code emits `ColonyCompleted` at the
bottom of `_run_colony()`. Move the emit AFTER crystallization returns its count.

In `colony_manager.py`, the sequence in `_run_colony` must be:

```python
async def _crystallize_skills(
    self,
    colony_id: str,
    task: str,
    final_summary: str,
    round_count: int,
) -> int:
    """Extract and store transferable skills. Returns count extracted."""
    if self._runtime.vector_store is None or self._runtime.embed_fn is None:
        return 0

    colony = self._runtime.projections.get_colony(colony_id)
    if colony is None:
        return 0

    # Resolve model for extraction (use the colony's queen model or default)
    model = self._runtime.resolve_model("archivist", colony.workspace_id)

    prompt = SKILL_EXTRACTION_PROMPT.format(
        task=task[:500],
        final_output=final_summary[:2000],
        rounds_completed=round_count,
    )

    try:
        response = await self._runtime.llm_router.complete(
            model=model,
            messages=[
                {"role": "system", "content": "You extract reusable skills from completed work. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception:
        log.warning("skill_crystallization.llm_failed", colony_id=colony_id)
        return 0

    # Parse JSON response (handle markdown fences, malformed JSON)
    skills = _parse_skills_json(response.content)
    if not skills:
        return 0

    # Build VectorDocuments
    docs: list[VectorDocument] = []
    timestamp = datetime.now(UTC).isoformat()
    for i, skill in enumerate(skills[:3]):  # cap at 3 skills per colony
        technique = skill.get("technique", "unknown")
        instruction = skill.get("instruction", "")
        if not instruction:
            continue
        docs.append(VectorDocument(
            id=f"skill-{colony_id}-{i}",
            content=f"{technique}: {instruction}",
            metadata={
                "technique": technique,
                "when_to_use": skill.get("when_to_use", ""),
                "failure_modes": skill.get("failure_modes", ""),
                "source_colony_id": colony_id,
                "source_task": task[:200],
                "confidence": 0.5,
                "extracted_at": timestamp,
            },
        ))

    if not docs:
        return 0

    count = await self._runtime.vector_store.upsert(
        collection="skill_bank", docs=docs,
    )
    log.info("skill_crystallization.complete",
             colony_id=colony_id, skills_extracted=count)
    return count


SKILL_EXTRACTION_PROMPT = """Given this completed colony's task and final output:

TASK: {task}
FINAL OUTPUT: {final_output}
ROUNDS COMPLETED: {rounds_completed}

Extract 1-3 reusable skills. Each skill must be transferable to future
colonies working on DIFFERENT tasks. Do not extract task-specific facts.

Return a JSON array only, no other text:
[
  {{
    "technique": "Short name for the technique",
    "when_to_use": "Conditions under which this technique applies",
    "instruction": "The minimal actionable instruction for a future agent",
    "failure_modes": "What can go wrong when applying this technique"
  }}
]

If no transferable skills are present, return []"""
```

### 4.2 JSON Parsing Helper

LLMs frequently wrap JSON in markdown fences or add preamble text.

```python
def _parse_skills_json(text: str) -> list[dict]:
    """Parse skills JSON from LLM output, handling common formatting issues."""
    import json
    import re

    # Strip markdown fences
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()

    # Find the array in the text (LLM may add preamble/postamble)
    bracket_start = text.find('[')
    bracket_end = text.rfind(']')
    if bracket_start == -1 or bracket_end == -1:
        return []

    json_str = text[bracket_start:bracket_end + 1]
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return []
```

---

## 5. Colony Quality Scoring (ADR-011)

### 5.1 Score Computation

```python
import math

def compute_quality_score(
    rounds_completed: int,
    max_rounds: int,
    convergence: float,
    governance_warnings: int,
    stall_rounds: int,
    completed_successfully: bool,
) -> float:
    """Composite quality score in [0.0, 1.0] using weighted geometric mean."""
    if not completed_successfully:
        return 0.0

    # Normalize each signal to (0, 1] where 1 = best
    round_efficiency = max(1.0 - (rounds_completed / max(max_rounds, 1)), 0.01)
    convergence_score = max(convergence, 0.01)
    governance_score = max(1.0 - (governance_warnings / 3.0), 0.01)
    stall_score = max(1.0 - (stall_rounds / max(rounds_completed, 1)), 0.01)

    # Weighted geometric mean (worst signal dominates)
    w = {"re": 0.25, "cs": 0.30, "gs": 0.25, "ss": 0.20}
    log_sum = (
        w["re"] * math.log(round_efficiency)
        + w["cs"] * math.log(convergence_score)
        + w["gs"] * math.log(governance_score)
        + w["ss"] * math.log(stall_score)
    )
    return round(math.exp(log_sum), 4)
```

### 5.2 Integration into Colony Manager

Track governance warnings and stall rounds in `_run_colony`:

```python
# Inside the round loop in _run_colony, existing variables extended:
governance_warnings = 0   # NEW counter
stall_count = 0           # already exists

# After each round result:
if result.governance.action == "warn":
    governance_warnings += 1
if result.convergence.is_stalled:
    stall_count += 1
else:
    stall_count = 0  # already exists

# At colony completion (both natural and max-rounds), before emitting:
quality = compute_quality_score(
    rounds_completed=round_num,
    max_rounds=colony.max_rounds,
    convergence=result.convergence.score,
    governance_warnings=governance_warnings,
    stall_rounds=stall_count,
    completed_successfully=True,
)
# Store on projection (see §5.3)
```

### 5.3 Projection and Snapshot Integration

Add `quality_score` to `ColonyProjection`:

```python
# In projections.py
@dataclass
class ColonyProjection:
    # ... existing fields ...
    quality_score: float = 0.0  # NEW
    skills_extracted: int = 0   # NEW — populated after crystallization
```

Update `_on_colony_completed` to store skills_extracted from the event.

In `view_state.py`, include both new fields in the colony node:

```python
colony_node = {
    # ... existing fields ...
    "qualityScore": colony.quality_score,    # NEW
    "skillsExtracted": colony.skills_extracted,  # NEW
}
```

---

## 6. Backend→Frontend Wiring Checklist

For every new piece of data, verify this complete chain:

```
1. Data source (runner, colony_manager, or projections)
   ↓
2. Stored on ColonyProjection (projections.py)
   ↓
3. Included in snapshot (view_state.py → colony_node dict)
   ↓
4. Typed in frontend (frontend/src/types.ts → ColonyNode interface)
   ↓
5. Applied in store (frontend/src/state/store.ts → event handler)
   ↓
6. Rendered in component (queen-overview.ts or colony-detail.ts)
```

### New fields to wire:

| Field | Python Source | Projection Field | Snapshot Key | TS Type | Component |
|-------|-------------|-----------------|--------------|---------|-----------|
| Quality score | `colony_manager._run_colony` | `ColonyProjection.quality_score` | `qualityScore` | `number` | queen-overview (dot), colony-detail (number) |
| Skills extracted | `colony_manager._crystallize_skills` | `ColonyProjection.skills_extracted` | `skillsExtracted` | `number` | queen-overview (badge), colony-detail (count) |
| Real cost | `runner._run_agent` via cost_fn | `ColonyProjection.cost` (already exists, now non-zero) | `cost` (already exists) | `number` (already exists) | colony-detail (already renders, now shows real $) |

### Config field additions:

`formicos.yaml` gains a `context` section (ADR-008) and `cost_per_input_token` /
`cost_per_output_token` on registry entries (ADR-009). These do NOT affect the
frontend — they are backend-only configuration.

### caste_recipes.yaml cleanup:

Remove tools that have no handler from caste tool lists. Keep only `memory_search`
and `memory_write` for castes that use them. The `queen` caste keeps its existing
tools (`spawn_colony`, `get_status`, etc.) which are MCP tools, not runner tools.

```yaml
castes:
  queen:
    tools: ["spawn_colony", "get_status", "query_memory", "kill_colony"]  # MCP tools, unchanged
  coder:
    tools: []  # no runner tools yet (code_execute deferred to sandbox)
  reviewer:
    tools: ["memory_search"]
  researcher:
    tools: ["memory_search", "memory_write"]
  archivist:
    tools: ["memory_search", "memory_write"]
```
