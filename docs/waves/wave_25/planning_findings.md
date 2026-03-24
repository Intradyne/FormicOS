# Wave 25 Planning Findings

**Wave:** 25 -- "Typed Transformations"
**Date:** 2026-03-17
**Purpose:** Repo-accurate observations that shaped the Wave 25 plan.

---

## Finding 1: AgentTurnCompleted stores only 200 chars of output

`runner.py` line 885:
```python
AgentTurnCompleted(
    ...
    output_summary=response.content[:200],
)
```

`events.py` line 220:
```python
output_summary: str = Field(..., description="Compressed turn output summary.")
```

The full agent output (`response.content`) is available in memory during execution via `RoundResult.outputs` (line 387: `outputs: dict[str, str]`), but only the first 200 chars are persisted in the event. Projections rebuild from events on startup.

**Implication:** Artifacts derived from full agent output during live execution would be lost on restart if they only live on the projection. Any artifact model that claims durability must persist artifacts through an event field.

## Finding 2: ColonyCompleted has a summary field but no structured output

`events.py` lines 155-165:
```python
class ColonyCompleted(EventEnvelope):
    colony_id: str
    summary: str = Field(..., description="Compressed final outcome summary.")
    skills_extracted: int
```

`colony_manager.py` line 571-575:
```python
await self._runtime.emit_and_broadcast(ColonyCompleted(
    seq=0, timestamp=_now(), address=address,
    colony_id=colony_id, summary=result.round_summary,
    skills_extracted=skills_count,
))
```

The `summary` is a compressed round summary. There is no structured output, artifact list, or typed result payload. Adding `artifacts: list[dict[str, Any]] = Field(default_factory=list)` to `ColonyCompleted` is additive and backward-compatible.

## Finding 3: RoundResult.outputs has full agent outputs in memory

`runner.py` lines 376-387:
```python
class RoundResult(BaseModel):
    round_number: int
    convergence: ConvergenceResult
    governance: GovernanceDecision
    cost: float
    duration_ms: int
    round_summary: str
    outputs: dict[str, str]
    ...
```

Line 842: `outputs[agent.id] = response.content` -- full content, not truncated.

`colony_manager.py` line 441: `result = await runner.run_round(...)` -- the colony_manager has access to `result.outputs` after each round. This is where live artifact extraction can hook in.

## Finding 4: Templates have no I/O description

`template_manager.py` lines 29-46:
```python
class ColonyTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    version: int = 1
    castes: list[CasteSlot]
    strategy: str = "stigmergic"
    budget_limit: float = 1.0
    max_rounds: int = 25
    tags: list[str] = []
    source_colony_id: str | None = None
    created_at: str = ""
    use_count: int = 0
```

No `input_description`, `output_description`, `expected_output_types`, or `completion_hint`. Templates currently describe team shape and resource allocation only.

All 7 built-in templates in `config/templates/` follow this shape. Adding optional string/list fields is non-breaking.

## Finding 5: InputSource has summary only

`core/types.py` lines 220-237:
```python
class InputSource(BaseModel):
    type: InputSourceType  # "colony" only
    colony_id: str
    summary: str = Field(default="", description="Resolved at spawn time.")
```

Colony chaining currently passes only a text summary. Adding `artifacts: list[dict[str, Any]] = Field(default_factory=list)` is additive and backward-compatible.

## Finding 6: Context assembly chains via summary text only

`context.py` lines 381-390:
```python
if input_sources:
    for src in input_sources:
        summary = src.get("summary", "")
        if summary:
            source_id = src.get("colony_id", "unknown")
            src_text = _truncate(
                f"[Context from prior colony {source_id}]:\n{summary}",
                budgets.max_per_source,
            )
            messages.append({"role": "user", "content": src_text})
```

Chained colonies receive only the summary text. Artifact metadata (type, name, preview) would give downstream colonies structured context about what the predecessor produced.

## Finding 7: Existing ToolCategory covers new effector needs

`core/types.py` lines 37-48:
```python
class ToolCategory(StrEnum):
    exec_code = "exec_code"
    read_fs = "read_fs"
    write_fs = "write_fs"
    vector_query = "vector_query"
    delegate = "delegate"
    search_web = "search_web"
    network_out = "network_out"
```

`network_out` already exists for outbound network calls. `read_fs` and `write_fs` already exist for filesystem operations. No new ToolCategory entries are needed:
- `http_fetch` --> `network_out`
- `file_read` --> `read_fs`
- `file_write` --> `write_fs`

## Finding 8: A2A has inline team-selection heuristics that duplicate Queen logic

`routes/a2a.py` contains keyword-matching heuristics for team selection (code keywords, review keywords, research keywords) that are structurally identical to logic the Queen prompt encourages. Both should share a common classifier rather than maintaining parallel implementations.

## Finding 9: ColonyProjection already has display_name and quality_score

`projections.py` line 86: `display_name: str | None = None`
`projections.py` line 84: `quality_score: float = 0.0`

Adding `artifacts: list[dict[str, Any]]` and `expected_output_types: list[str]` follows the existing pattern of projection fields that accumulate during execution and are consumed by surface-layer renderers.

## Finding 10: Caste policies are hardcoded in runner.py

`runner.py` lines 167-199: `CASTE_TOOL_POLICIES` dict with per-caste `CasteToolPolicy`. Adding `network_out` to coder and researcher policies requires changing only these dict entries. No new infrastructure needed.

## Finding 11: Tool handlers currently return strings, not structured side effects

`runner.py` routes tools through `_execute_tool()`, which returns a `str` back into the agent loop.

**Implication for Wave 25:** `file_write` should stay narrow. It can write a named deliverable to the workspace file surface and return a confirmation string, but it should not pretend to be a second artifact-persistence channel unless the runner/tool interface is widened intentionally. Artifact truth should remain concentrated in Track A's `ColonyCompleted.artifacts` path.
