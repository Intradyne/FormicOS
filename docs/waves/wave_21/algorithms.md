# Wave 21 Algorithms - Implementation Reference

**Wave:** 21 - "Alpha Complete"  
**Purpose:** Technical guide for the Wave 21 implementation tracks. This document is intentionally practical and repo-shaped.

---

## 1. Capability Registry

### Design rule

Declared truth, validated separately.

The registry is built during app assembly from explicit manifests and mounted surfaces. It should not scrape Starlette route tables or reach into FastMCP private internals just to discover what the system already knows.

### Data model

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolEntry:
    name: str
    description: str


@dataclass(frozen=True)
class ProtocolEntry:
    name: str
    status: str
    endpoint: str | None = None
    transport: str | None = None
    semantics: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CapabilityRegistry:
    event_names: tuple[str, ...]
    mcp_tools: tuple[ToolEntry, ...]
    queen_tools: tuple[ToolEntry, ...]
    agui_events: tuple[str, ...]
    protocols: tuple[ProtocolEntry, ...]
    castes: tuple[str, ...]
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "events": {
                "count": len(self.event_names),
                "names": list(self.event_names),
            },
            "mcp": {
                "tools": len(self.mcp_tools),
                "entries": [
                    {"name": t.name, "description": t.description}
                    for t in self.mcp_tools
                ],
            },
            "queen": {
                "tools": len(self.queen_tools),
                "entries": [
                    {"name": t.name, "description": t.description}
                    for t in self.queen_tools
                ],
            },
            "agui": {
                "events": len(self.agui_events),
                "names": list(self.agui_events),
            },
            "protocols": [
                {
                    key: value
                    for key, value in {
                        "name": p.name,
                        "status": p.status,
                        "endpoint": p.endpoint,
                        "transport": p.transport,
                        "semantics": p.semantics,
                        "note": p.note,
                    }.items()
                    if value is not None
                }
                for p in self.protocols
            ],
            "castes": list(self.castes),
        }
```

### App-factory wiring

Build the registry after:

- settings
- castes
- runtime
- MCP surface
- Queen runtime

exist

and before route assembly finalizes.

The registry should then be stored on:

- `app.state.registry`

### MCP manifest source

Do not inspect `mcp._tool_manager`.

Preferred shape in `mcp_server.py`:

```python
MCP_TOOL_ENTRIES = (
    {"name": "list_workspaces", "description": "List all workspaces."},
    {"name": "get_status", "description": "Get workspace status including threads and colonies."},
    ...
)

MCP_TOOL_NAMES = tuple(entry["name"] for entry in MCP_TOOL_ENTRIES)
```

Then registry construction can use that explicit manifest directly.

### Queen manifest source

Use the existing `_queen_tools()` output.

That is already a structured tool manifest and is the right source for registry population.

---

## 2. Event Manifest and Parity

### Python event manifest

Add an explicit `EVENT_TYPE_NAMES` constant in `events.py`.

Keep it simple and explicit.

```python
EVENT_TYPE_NAMES = [
    "WorkspaceCreated",
    "ThreadCreated",
    ...
    "ColonyRedirected",
]
```

### Self-check

It is reasonable for Wave 21 to include a small import-time self-check that compares the manual manifest with the actual union members.

That check should fail loudly and clearly if the manifest drifts.

### TypeScript event manifest

Add:

```typescript
export const EVENT_NAMES = [
  'WorkspaceCreated',
  'ThreadCreated',
  // ...
  'ColonyRedirected',
] as const;
```

### Parity tests

Add a new parity test module that compares:

- `EVENT_TYPE_NAMES`
- `EVENT_NAMES`
- registry MCP tool names
- registry Queen tool names
- registry AG-UI event names

This test should compare manifests, not parse implementation details.

---

## 3. `input_sources` Projection Fix

### Current issue

`ColonySpawned` already carries `input_sources`, but `ColonyProjection` still does not persist it.

`transcript.py` therefore falls back to:

```python
getattr(colony, "input_sources", [])
```

and chained-colony transcript attribution can remain empty.

### Fix

Add to `ColonyProjection`:

```python
input_sources: list[dict[str, Any]] = field(default_factory=list)
```

Then populate it in the colony-spawn handler from `event.input_sources`.

This is a small change with outsized truthfulness value.

---

## 4. Queen Tool: `read_colony_output`

### Intent

Close the gap between:

- what the UI can inspect in round/agent output
- what the Queen can currently discuss

### Behavior

- `colony_id` required
- `round_number` optional, default latest completed round
- `agent_id` optional, default all agents in that round
- truncate each agent output to a bounded limit such as 4000 chars
- include context like caste/model/tool calls when available

### Shape

Suggested response format:

```text
Colony: colony-123
Round: 4

--- agent-a (coder) ---
Model: llama-cpp/...
Tools: memory_search, code_execute

<output text>
```

If the round or agent is missing, return a clean rejection with available choices.

---

## 5. Queen Tool: `search_memory`

### Design rule

Reuse the current memory-search behavior. Do not create a new retrieval policy.

### Existing pattern

The current memory search already queries:

- skill bank collection
- workspace memory collection

and then deduplicates and sorts results.

Wave 21 should keep that exact shape for Queen search.

### Acceptable implementation shape

```python
skill_collection = ...
results = []
for collection in (skill_collection, workspace_id):
    try:
        hits = await vector_port.search(
            collection=collection,
            query=query,
            top_k=top_k,
        )
        results.extend(hits)
    except Exception:
        pass
```

If extracting a shared helper is easy and does not distort layer boundaries, that is fine. If not, a tiny duplicate loop is acceptable. Truthful reuse matters more than DRY purity here.

### Output

Return:

- content preview
- confidence/score if present
- source colony if present
- extraction/freshness timestamp if present

This is enough for operator-facing recall without inventing extra semantics.

---

## 6. Queen Tool: `write_workspace_file`

### Canonical path

Use the same path the current workspace file routes already expose:

- `data/workspaces/{workspace_id}/files/`

### Guardrails

- extension whitelist
- max size cap
- strip path traversal with `Path(filename).name`
- create directory if missing
- allow overwrite

Suggested extensions:

- `.md`
- `.txt`
- `.json`
- `.yaml`
- `.yml`
- `.csv`

### Important alignment note

The current Queen read path is slightly broader than the HTTP `/files/` surface. While touching this area, prefer a coherent Queen read/write story over keeping the mismatch forever.

---

## 7. Queen Tool: `queen_note`

### Storage

Per-workspace YAML file, for example:

- `data/workspaces/{workspace_id}/queen_notes.yaml`

Suggested structure:

```yaml
notes:
  - content: "Operator prefers 3-coder teams for code tasks"
    timestamp: "2026-03-16T12:00:00Z"
```

### Bounds

- max 50 notes total
- max 500 chars per note
- latest 10 injected into context

### Context injection

Inject the latest notes immediately after the main system prompt, before the active conversation history.

That gives the notes high visibility without turning them into permanent unbounded baggage.

---

## 8. Iteration Bump

Raise:

- `_MAX_TOOL_ITERATIONS = 7`

That is enough room for multi-step Queen workflows without making the loop feel unconstrained.

Model-aware scaling can be documented as optional stretch only.

---

## 9. Route Extraction

### Pattern

Each route module should export a route-builder function that accepts explicit dependencies and returns a route list.

Example shape:

```python
def routes(*, runtime, projections, settings, registry, data_dir, **_unused):
    async def health(request):
        ...

    return [
        Route("/health", health),
    ]
```

### Route groups

Recommended grouping:

- `health.py`
  - `/health`
  - `/debug/inventory`
- `api.py`
  - skills
  - knowledge
  - retrieval diagnostics
  - suggest-team
  - templates
  - castes
  - model policy
- `colony_io.py`
  - colony files
  - export
  - transcript
  - workspace files
- `protocols.py`
  - Agent Card
  - AG-UI route
  - MCP mount

### Rule

This is a mechanical extraction. Route behavior should remain unchanged.

---

## 10. Registry Consumers

After the registry exists, protocol truth should come from it.

Primary consumers:

- `view_state._build_protocol_status()`
- Agent Card builder
- `/debug/inventory`

This should eliminate the remaining duplicated protocol facts from Wave 20.

---

## 11. Evaluation Harness

### Task format

Suggested YAML shape:

```yaml
id: email-validator
description: "Write a Python function that validates email addresses with comprehensive tests"
difficulty: simple
castes:
  - caste: coder
    tier: standard
  - caste: reviewer
    tier: standard
success_rubric: |
  - Function handles edge cases
  - Tests cover at least 10 cases
  - Code is clean and documented
budget_limit: 1.0
max_rounds: 10
model_assignments: {}
```

### Harness behavior

Prefer in-process execution:

- spawn colony through runtime
- start colony
- wait for terminal status
- build transcript directly
- record result artifact

Hold constant:

- models
- budget
- max rounds
- team composition
- task description

Only vary:

- coordination strategy

### Result artifact

Each run should record at minimum:

- task id
- strategy
- colony id
- status
- quality score
- cost
- wall time
- rounds completed
- tool-call summary
- retrieved skill/chaining evidence
- transcript

### Comparison artifact

Generate:

- markdown summary
- JSON result bundle

and include an explicit disclaimer that the first version is exploratory and not statistically significant.

No frontend panel is required.

---

## 12. Recommended File Changes

### Track A

- `src/formicos/surface/registry.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/mcp_server.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/types.ts`
- parity/Queen-tool tests

### Track B

- `src/formicos/surface/routes/__init__.py`
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/routes/colony_io.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/routes/health.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/view_state.py`
- optional `src/formicos/surface/view_helpers.py`

### Track C

- `config/eval/tasks/*.yaml`
- `src/formicos/eval/__init__.py`
- `src/formicos/eval/run.py`
- `src/formicos/eval/compare.py`

---

## 13. Final Guidance

The easiest way for Wave 21 to go wrong is to become more ambitious than the repo needs.

Keep these boundaries:

- registry over introspection
- reuse over new retrieval architecture
- script/report over frontend evaluation UI
- mechanical extraction over surface rewrite

If the implementation stays inside those bounds, Wave 21 will feel like an alpha milestone instead of a sprawling cleanup wave.
