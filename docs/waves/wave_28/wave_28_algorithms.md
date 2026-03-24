# Wave 28 Algorithms -- Implementation Reference

**Wave:** 28 -- "Knowledge Runtime Unification"
**Purpose:** Technical implementation guide for all three tracks.

---

## S1. KnowledgeAccessItem Type (Track B -- B1)

### In core/types.py

```python
class KnowledgeAccessItem(BaseModel):
    """Single knowledge item accessed during a colony round (Wave 28).

    Used end-to-end: ContextResult -> RoundResult -> KnowledgeAccessRecorded event.
    """
    model_config = FrozenConfig

    id: str = Field(description="Knowledge item ID (mem-* for institutional, UUID for legacy)")
    source_system: str = Field(description="legacy_skill_bank | institutional_memory")
    canonical_type: str = Field(description="skill | experience")
    title: str = Field(default="")
    confidence: float = Field(default=0.5)
    score: float = Field(default=0.0, description="Query relevance score from retrieval")
```

Add to `__all__`.

---

## S2. KnowledgeAccessRecorded Event (Track B -- B1)

### In core/events.py

```python
class KnowledgeAccessRecorded(EventEnvelope):
    """Knowledge items accessed during a colony round (Wave 28).

    Emitted by colony_manager after each run_round() returns.
    Carries the round's aggregated knowledge_items_used from RoundResult.
    """
    model_config = FrozenConfig

    type: Literal["KnowledgeAccessRecorded"] = "KnowledgeAccessRecorded"
    colony_id: str = Field(..., description="Colony that accessed knowledge.")
    round_number: int = Field(..., ge=1, description="Round number.")
    workspace_id: str = Field(..., description="Workspace scope.")
    access_mode: str = Field(
        default="context_injection",
        description="context_injection | tool_search | tool_detail. Wave 28: context_injection only.",
    )
    items: list[KnowledgeAccessItem] = Field(
        default_factory=list,
        description="Knowledge items that were injected into agent context.",
    )
```

### Union update

```python
FormicOSEvent: TypeAlias = Annotated[
    Union[
        # ... existing 40 ...
        KnowledgeAccessRecorded,  # Wave 28
    ],
    Field(discriminator="type"),
]
```

### In core/ports.py

Add `"KnowledgeAccessRecorded"` to `EventTypeName` literal (40 -> 41).

---

## S3. ContextResult + RoundResult Extensions (Track A -- A3, A4)

### In engine/context.py -- ContextResult

```python
class ContextResult(BaseModel):
    """Return type for assemble_context -- messages plus retrieval metadata."""
    model_config = ConfigDict(frozen=True)

    messages: list[LLMMessage]
    retrieved_skill_ids: list[str] = []
    knowledge_items_used: list[KnowledgeAccessItem] = []  # Wave 28
```

Import `KnowledgeAccessItem` from `formicos.core.types` (core import -- layer-safe).

### In engine/runner.py -- RoundResult

```python
class RoundResult(BaseModel):
    model_config = _FrozenCfg
    round_number: int
    convergence: ConvergenceResult
    governance: GovernanceDecision
    cost: float
    duration_ms: int
    round_summary: str
    outputs: dict[str, str]
    updated_weights: dict[tuple[str, str], float]
    retrieved_skill_ids: list[str] = []
    knowledge_items_used: list[KnowledgeAccessItem] = []  # Wave 28
```

Import `KnowledgeAccessItem` from `formicos.core.types` (core import -- layer-safe).

---

## S4. Unified Knowledge Fetch (Track A -- A1)

### In surface/runtime.py

```python
async def fetch_knowledge_for_colony(
    self,
    task: str,
    workspace_id: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Fetch unified knowledge items from the catalog for agent context injection.

    Returns normalized KnowledgeItem dicts from the Wave 27 knowledge catalog.
    Called by colony_manager before each round.
    """
    catalog = getattr(self, "knowledge_catalog", None)
    if catalog is None:
        return []
    try:
        return await catalog.search(
            query=task, workspace_id=workspace_id, top_k=top_k,
        )
    except Exception:
        log.debug("runtime.knowledge_fetch_failed", task=task[:80])
        return []
```

### Callback factories for progressive disclosure tools

```python
def make_knowledge_detail_fn(self) -> Callable[..., Awaitable[str]] | None:
    """Create a callback for the knowledge_detail agent tool."""
    catalog = getattr(self, "knowledge_catalog", None)
    if catalog is None:
        return None

    async def _knowledge_detail(item_id: str) -> str:
        result = await catalog.get_by_id(item_id)
        if result is None:
            return f"Error: knowledge item '{item_id}' not found"
        content = result.get("content_preview", "") or result.get("summary", "")
        title = result.get("title", "")
        source = result.get("source_system", "")
        return (
            f"[{result.get('canonical_type', 'skill').upper()}, {source}] "
            f"{title}\n\n{content}"
        )

    return _knowledge_detail

def make_artifact_inspect_fn(self) -> Callable[..., Awaitable[str]] | None:
    """Create a callback for the artifact_inspect agent tool."""
    projections = self.projections

    async def _artifact_inspect(colony_id: str, artifact_id: str) -> str:
        colony = projections.get_colony(colony_id)
        if colony is None:
            return f"Error: colony '{colony_id}' not found"
        for art in colony.artifacts:
            art_dict = art if isinstance(art, dict) else {}
            if art_dict.get("id") == artifact_id:
                name = art_dict.get("name", "unnamed")
                atype = art_dict.get("artifact_type", "generic")
                content = art_dict.get("content", "")
                return f"[Artifact: {name} ({atype})]\n\n{content[:5000]}"
        return f"Error: artifact '{artifact_id}' not found in colony '{colony_id}'"

    return _artifact_inspect

def make_catalog_search_fn(self) -> Callable[..., Awaitable[list[dict[str, Any]]]] | None:
    """Create a callback for the repointed memory_search agent tool."""
    catalog = getattr(self, "knowledge_catalog", None)
    if catalog is None:
        return None

    async def _catalog_search(
        query: str, workspace_id: str, top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return await catalog.search(
            query=query, workspace_id=workspace_id, top_k=top_k,
        )

    return _catalog_search
```

---

## S5. Threading Knowledge Through the Engine (Track A -- A2, A3)

### In colony_manager.py -- before the round loop

```python
# Fetch unified knowledge for the colony task (Wave 28 A1)
knowledge_items = await self._runtime.fetch_knowledge_for_colony(
    task=colony.active_goal or colony.task,
    workspace_id=colony.workspace_id,
    top_k=5,
)

# Build RoundRunner with catalog callbacks (Wave 28 A5/A6)
runner = RoundRunner(
    emit=self._runtime.emit_and_broadcast,
    # ... existing args ...
    catalog_search_fn=self._runtime.make_catalog_search_fn(),
    knowledge_detail_fn=self._runtime.make_knowledge_detail_fn(),
    artifact_inspect_fn=self._runtime.make_artifact_inspect_fn(),
)
```

### In the round loop

```python
result = await runner.run_round(
    colony_context=ctx,
    # ... existing args ...
    knowledge_items=knowledge_items,  # Wave 28 A2
)
```

### In runner.py -- run_round signature

```python
async def run_round(
    self,
    colony_context: ColonyContext,
    agents: Sequence[AgentConfig],
    strategy: CoordinationStrategy,
    llm_port: LLMPort,
    vector_port: VectorPort | None,
    event_store_address: str,
    budget_limit: float = 5.0,
    total_colony_cost: float = 0.0,
    routing_override: dict[str, Any] | None = None,
    knowledge_items: list[dict[str, Any]] | None = None,  # Wave 28
) -> RoundResult:
```

Thread `knowledge_items` into `_run_agent()`:

```python
tg.create_task(
    self._run_agent(
        agent, colony_context, round_goal,
        outputs, agent_costs, round_skill_ids,
        llm_port, vector_port,
        event_store_address, round_num,
        # ... existing args ...
        knowledge_items=knowledge_items,  # Wave 28
    )
)
```

### In runner.py -- _run_agent signature

```python
async def _run_agent(
    self,
    # ... existing params ...
    knowledge_items: list[dict[str, Any]] | None = None,  # Wave 28
) -> None:
```

Pass to assemble_context:

```python
ctx_result = await assemble_context(
    agent=agent,
    colony_context=colony_context,
    round_goal=round_goal,
    routed_outputs=outputs,
    merged_summaries=[],
    vector_port=vector_port,
    budget_tokens=agent.recipe.max_tokens,
    tier_budgets=self._tier_budgets,
    kg_adapter=self._kg_adapter,
    knowledge_items=knowledge_items,  # Wave 28
)
messages = list(ctx_result.messages)
round_skill_ids.extend(ctx_result.retrieved_skill_ids)
```

### In runner.py -- aggregate per-agent usage into RoundResult

After all agents complete in run_round(), aggregate knowledge usage:

```python
# Aggregate knowledge items used across all agents (Wave 28 A4)
# _round_knowledge_items_used is populated during _run_agent calls
# by appending each agent's ctx_result.knowledge_items_used

return RoundResult(
    # ... existing fields ...
    knowledge_items_used=_deduplicated_knowledge_items,  # Wave 28
)
```

The simplest approach: add a shared list alongside `round_skill_ids` in run_round(), extend it from each `_run_agent` call, deduplicate by `id` before returning.

---

## S6. System Knowledge Tier in context.py (Track A -- A3)

### In assemble_context()

Add parameter:

```python
async def assemble_context(
    # ... existing params ...
    knowledge_items: list[dict[str, Any]] | None = None,  # Wave 28
) -> ContextResult:
```

New tier between input sources (2b) and routed outputs (3):

```python
    # Tier 2c: Unified system knowledge (Wave 28)
    skip_legacy_skills = False
    knowledge_access_items: list[KnowledgeAccessItem] = []

    if knowledge_items:
        lines = ["[System Knowledge]"]
        for item in knowledge_items[:5]:
            source = "LEGACY" if item.get("source_system") == "legacy_skill_bank" else "INST"
            ctype = str(item.get("canonical_type", "skill")).upper()
            status = str(item.get("status", "")).upper()
            title = item.get("title", "")
            content = str(item.get("content_preview", ""))[:250]
            conf = float(item.get("confidence", 0.5))
            lines.append(f'[{ctype}, {status}, {source}] "{title}": {content}')
            lines.append(f"  confidence: {conf:.1f}")

            # Build typed access record
            knowledge_access_items.append(KnowledgeAccessItem(
                id=item.get("id", ""),
                source_system=item.get("source_system", ""),
                canonical_type=item.get("canonical_type", "skill"),
                title=title,
                confidence=conf,
                score=float(item.get("score", 0.0)),
            ))

        knowledge_text = _truncate("\n".join(lines), budgets.skill_bank)
        messages.append({"role": "user", "content": knowledge_text})
        skip_legacy_skills = True
```

Then guard the existing Tier 6 block:

```python
    # 6. Skill bank -- legacy retrieval (Wave 28: fallback only)
    if vector_port is not None and not skip_legacy_skills:
        try:
            # ... existing RetrievalPipeline / skill_bank_v2 code unchanged ...
```

Return with the new field:

```python
    return ContextResult(
        messages=messages,
        retrieved_skill_ids=retrieved_skill_ids,
        knowledge_items_used=knowledge_access_items,  # Wave 28
    )
```

---

## S7. New Agent Tools (Track A -- A6)

### Tool specs in runner.py

```python
TOOL_SPECS["knowledge_detail"] = {
    "name": "knowledge_detail",
    "description": (
        "Retrieve the full content of a knowledge item by its ID. "
        "Use when the context preview is insufficient and you need the complete entry."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "Knowledge item ID (e.g., mem-abc-s-0)",
            },
        },
        "required": ["item_id"],
    },
}
TOOL_CATEGORY_MAP["knowledge_detail"] = ToolCategory.vector_query

TOOL_SPECS["artifact_inspect"] = {
    "name": "artifact_inspect",
    "description": (
        "Inspect the content of a specific artifact produced by a prior colony. "
        "Useful for reviewing code, documents, or other outputs from predecessor work."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "colony_id": {
                "type": "string",
                "description": "Colony that produced the artifact",
            },
            "artifact_id": {
                "type": "string",
                "description": "Artifact ID (e.g., art-colony-agent-r3-0)",
            },
        },
        "required": ["colony_id", "artifact_id"],
    },
}
TOOL_CATEGORY_MAP["artifact_inspect"] = ToolCategory.read_fs
```

### RoundRunner.__init__ extensions

```python
class RoundRunner:
    def __init__(
        self,
        # ... existing params ...
        catalog_search_fn: Callable[..., Any] | None = None,      # Wave 28
        knowledge_detail_fn: Callable[..., Any] | None = None,    # Wave 28
        artifact_inspect_fn: Callable[..., Any] | None = None,    # Wave 28
    ) -> None:
        # ... existing assignments ...
        self._catalog_search_fn = catalog_search_fn
        self._knowledge_detail_fn = knowledge_detail_fn
        self._artifact_inspect_fn = artifact_inspect_fn
```

### _execute_tool dispatch additions

```python
    async def _execute_tool(self, tool_name, arguments, ...):
        # ... existing dispatch ...

        if tool_name == "memory_search":
            return await _handle_memory_search(
                vector_port, workspace_id, colony_id, arguments,
                catalog_search_fn=self._catalog_search_fn,  # Wave 28
            )

        if tool_name == "knowledge_detail":
            if self._knowledge_detail_fn is None:
                return "Error: knowledge_detail not available"
            item_id = arguments.get("item_id", "")
            if not item_id:
                return "Error: item_id is required"
            return await self._knowledge_detail_fn(item_id)

        if tool_name == "artifact_inspect":
            if self._artifact_inspect_fn is None:
                return "Error: artifact_inspect not available"
            colony_id_arg = arguments.get("colony_id", "")
            artifact_id = arguments.get("artifact_id", "")
            if not colony_id_arg or not artifact_id:
                return "Error: colony_id and artifact_id are required"
            return await self._artifact_inspect_fn(colony_id_arg, artifact_id)

        # ... rest of existing dispatch ...
```

---

## S8. Repointed memory_search Handler (Track A -- A5)

### Modified _handle_memory_search

```python
async def _handle_memory_search(
    vector_port: VectorPort,
    workspace_id: str,
    colony_id: str,
    arguments: dict[str, Any],
    catalog_search_fn: Callable[..., Any] | None = None,  # Wave 28
) -> str:
    """Execute memory_search tool call.

    Search order: scratch_{colony_id} -> workspace -> knowledge catalog.
    Falls back to legacy skill_bank_v2 if no catalog callback.
    """
    query = arguments.get("query", "")
    top_k = min(arguments.get("top_k", 5), 10)

    if not query:
        return "Error: query is required"

    results: list[VectorSearchHit] = []

    # 1. Colony scratch (always first -- most specific)
    scratch_coll = f"scratch_{colony_id}"
    try:
        hits = await vector_port.search(collection=scratch_coll, query=query, top_k=top_k)
        results.extend(hits)
    except Exception:
        pass

    # 2. Workspace memory
    try:
        hits = await vector_port.search(collection=workspace_id, query=query, top_k=top_k)
        results.extend(hits)
    except Exception:
        pass

    # 3. Knowledge catalog (replaces legacy skill_bank_v2-only search)
    catalog_parts: list[str] = []
    if catalog_search_fn is not None:
        try:
            catalog_results = await catalog_search_fn(
                query=query, workspace_id=workspace_id, top_k=top_k,
            )
            for i, item in enumerate(catalog_results, 1):
                source = "LEGACY" if item.get("source_system") == "legacy_skill_bank" else "INST"
                title = item.get("title", "")
                preview = str(item.get("content_preview", ""))[:400]
                catalog_parts.append(f"[{i}] [{source}] {title}: {preview}")
        except Exception:
            pass
    else:
        # Fallback: legacy skill_bank_v2 only (no catalog available)
        skill_coll = str(getattr(vector_port, "_default_collection", "skill_bank_v2"))
        try:
            hits = await vector_port.search(collection=skill_coll, query=query, top_k=top_k)
            results.extend(hits)
        except Exception:
            pass

    # Format combined results
    if not results and not catalog_parts:
        return "No results found."

    parts: list[str] = []

    # Vector results (scratch + workspace)
    seen: set[str] = set()
    unique: list[VectorSearchHit] = []
    for hit in results:
        if hit.id not in seen:
            seen.add(hit.id)
            unique.append(hit)
    unique.sort(key=lambda h: h.score)
    for i, hit in enumerate(unique[:top_k], 1):
        parts.append(f"[{i}] {hit.content[:500]}")

    # Catalog results (unified knowledge)
    if catalog_parts:
        parts.append("\n--- System Knowledge ---")
        parts.extend(catalog_parts)

    return "\n\n".join(parts)
```

---

## S9. Projection Handler (Track B -- B2)

### In projections.py

```python
# Add to ColonyProjection:
knowledge_accesses: list[dict[str, Any]] = field(default_factory=list)  # Wave 28


# Handler:
def _on_knowledge_access_recorded(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeAccessRecorded = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.knowledge_accesses.append({
            "round": e.round_number,
            "access_mode": e.access_mode,
            "items": [item.model_dump() for item in e.items],
        })
```

Register in `_HANDLERS`:

```python
"KnowledgeAccessRecorded": _on_knowledge_access_recorded,
```

---

## S10. Trace Emission (Track B -- B3)

### In colony_manager.py -- after run_round() returns

```python
# Emit knowledge access trace (Wave 28 B3)
if result.knowledge_items_used:
    from formicos.core.events import KnowledgeAccessRecorded
    await self._runtime.emit_and_broadcast(KnowledgeAccessRecorded(
        seq=0, timestamp=_now(), address=address,
        colony_id=colony_id,
        round_number=round_num,
        workspace_id=colony.workspace_id,
        access_mode="context_injection",
        items=result.knowledge_items_used,
    ))
```

This goes immediately after the existing `round_skill_ids.update(...)` line, before governance checks.

---

## S11. Transcript Exposure (Track B -- B4)

### In transcript.py -- build_transcript()

```python
# Knowledge access trace (Wave 28)
if colony.knowledge_accesses:
    result["knowledge_trace"] = colony.knowledge_accesses
```

This is additive. The transcript gains a `knowledge_trace` field when accesses exist.

---

## S12. Legacy Decommission Points (Track C)

### C1: Disable crystallization (colony_manager.py)

Two locations to change:

**Line ~568 (convergence completion path):**
```python
# Legacy skill crystallization disabled (Wave 28).
# Institutional memory extraction is the sole active knowledge write path.
# skill_bank_v2 continues as read-only archival data via the knowledge catalog.
skills_count = 0
```

**Line ~634 (max-rounds completion path):**
```python
# Legacy skill crystallization disabled (Wave 28).
skills_count = 0
```

### C2: Disable confidence updates (colony_manager.py _post_colony_hooks)

```python
    # Legacy confidence update disabled (Wave 28).
    # Institutional memory confidence will be handled by Wave 29.
    skills_updated = 0
    # if retrieved_skill_ids and self._runtime.vector_store is not None:
    #     ... (existing code preserved as comment) ...

    # Legacy SkillConfidenceUpdated emission disabled (Wave 28).
    # if _HAS_CONFIDENCE_EVENT and skills_updated > 0:
    #     ... (existing code preserved as comment) ...
```

### C3: Remove Queen tools (queen_runtime.py)

Remove from `_queen_tools()` return list:
- the `list_skills` tool spec dict
- the `search_memory` tool spec dict

Remove from tool dispatch in `_execute_tool_call()`:
- `if name == "list_skills":` branch
- `if name == "search_memory":` branch

Remove handler methods:
- `_tool_list_skills()`
- `_tool_search_memory()`

### C4: Remove /api/v1/skills (routes/api.py)

Remove:
- `get_skills` handler function
- `Route("/api/v1/skills", get_skills)` from the routes list
- `get_skill_bank_detail` import if no longer used elsewhere

### C5: Remove dead imports

**formicos-app.ts:**
```typescript
// Remove this line:
import './skill-browser.js';
```

**knowledge-view.ts:**
```typescript
// Remove this line:
import './skill-browser.js';
// The component becomes graph-only.
// If it rendered a skill browser section, remove that render block.
```

---

## S13. Caste Recipe Updates (Track A -- A7, Track C -- C3)

### Track A adds new tools

```yaml
  coder:
    tools: ["memory_search", "memory_write", "code_execute", "knowledge_detail", "artifact_inspect"]

  reviewer:
    tools: ["memory_search", "knowledge_detail", "artifact_inspect"]

  researcher:
    tools: ["memory_search", "memory_write", "knowledge_detail", "artifact_inspect"]

  archivist:
    tools: ["memory_search", "memory_write", "knowledge_detail", "artifact_inspect"]
```

### Track C removes legacy Queen tools

```yaml
  queen:
    tools: ["spawn_colony", "kill_colony", "redirect_colony", "escalate_colony", "inspect_colony", "get_status", "list_templates", "inspect_template", "memory_search", "read_workspace_files", "write_workspace_file", "read_colony_output", "suggest_config_change", "approve_config_change", "queen_note"]
```

Note: `list_skills` and `search_memory` removed. `memory_search` stays.

Also update the Queen system prompt tool count and listing to remove references to `list_skills` and `search_memory`.

---

## S14. Frontend Types (Track B -- B4)

### In types.ts

```typescript
export interface KnowledgeAccessItemPreview {
  id: string;
  source_system: string;
  canonical_type: string;
  title: string;
  confidence: number;
  score: number;
}

export interface KnowledgeAccessTrace {
  round: number;
  access_mode: string;
  items: KnowledgeAccessItemPreview[];
}
```

---

## S15. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/surface/runtime.py` | `fetch_knowledge_for_colony()` + 3 callback factories (~60 LOC) |
| `src/formicos/surface/colony_manager.py` | fetch knowledge, inject callbacks into RoundRunner (~20 LOC) |
| `src/formicos/engine/runner.py` | thread knowledge_items, repoint memory_search, add tools, extend RoundResult, callbacks on __init__ (~80 LOC) |
| `src/formicos/engine/context.py` | [System Knowledge] tier, extend ContextResult (~40 LOC) |
| `config/caste_recipes.yaml` | add knowledge_detail + artifact_inspect to 4 castes (~8 lines) |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | KnowledgeAccessItem (~10 LOC) |
| `src/formicos/core/events.py` | KnowledgeAccessRecorded, union 40->41 (~15 LOC) |
| `src/formicos/core/ports.py` | add event name (~1 LOC) |
| `src/formicos/surface/projections.py` | knowledge_accesses field + handler (~15 LOC) |
| `src/formicos/surface/colony_manager.py` | emit trace post-round (~10 LOC) |
| `src/formicos/surface/transcript.py` | expose trace (~5 LOC) |
| `frontend/src/components/colony-detail.ts` | "Knowledge Used" section (~25 LOC) |
| `frontend/src/types.ts` | access trace types (~15 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/surface/colony_manager.py` | disable crystallization + confidence (~15 LOC changed) |
| `src/formicos/surface/queen_runtime.py` | remove search_memory + list_skills (~net -80 LOC) |
| `config/caste_recipes.yaml` | remove legacy Queen tools + update prompt (~10 lines) |
| `src/formicos/surface/routes/api.py` | remove /api/v1/skills (~net -15 LOC) |
| `frontend/src/components/formicos-app.ts` | remove skill-browser import (~1 LOC) |
| `frontend/src/components/knowledge-view.ts` | remove skill-browser, graph-only (~5 LOC) |
| `frontend/src/components/colony-detail.ts` | de-emphasize skills_extracted (~5 LOC) |
| `tests/*` | event count + removed endpoint/tool assertions |
