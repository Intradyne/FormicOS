# Wave 25 Plan -- Typed Transformations

**Wave:** 25 -- "Typed Transformations"
**Theme:** Colonies produce typed artifacts, not text blobs. Templates become task contracts. The Queen reasons about transformations, not just teams. FormicOS transitions from a strong multi-agent runner into a composable execution engine whose advantage is reasoning well about what work actually is.
**Architectural thesis:** Context as environment, work as typed transformation.
**Contract changes:** 0 new event types. Additive optional field `artifacts` on `ColonyCompleted` for replay-safe persistence. Additive `artifacts` field on `InputSource` for chaining. Additive types `Artifact` and `ArtifactType` in `core/types.py`. Templates gain optional contract fields. No new ports.
**Estimated LOC delta:** ~450 Python, ~40 TypeScript, ~60 config/templates

---

## Why This Wave

FormicOS is already structurally similar to the Recursive Language Model paradigm: a root coordinator (Queen) decomposes work, spawns isolated sub-executors (colonies) that operate in scoped environments (colony scratch + workspace library + skill bank), with results aggregating through a shared substrate (transcripts, memory, chaining). The dual-model economics (expensive coordinator, cheap workers) already maps to Queen-on-heavy, workers-on-light tier routing.

The architecture is sound. The gap is that **the shared substrate is still text.**

- Colony outputs are strings (`response.content` truncated to 200 chars in `AgentTurnCompleted.output_summary`, runner.py line 885)
- Colony chaining passes a compressed summary (`InputSource.summary` in context.py line 381)
- Templates describe teams but not what goes in or comes out (`ColonyTemplate` has `castes`, `strategy`, `budget_limit` -- no I/O description)
- A2A returns transcript blobs. The Queen reasons about team composition but not output shape.

Typed artifacts are the FormicOS equivalent of RLM REPL variables -- not a storage feature but a **reasoning substrate**. Once a colony produces `{name: "email_validator.py", type: code, source: colony-abc}`, the Queen can reason in a different mode:
- not "that colony wrote something"
- but "that colony produced a code artifact and a test artifact -- the contract is satisfied"
- not "spawn a coder"
- but "transform requirements into tested code"

This wave introduces three layers: the **artifact model** (typed outputs as reasoning objects), **task contracts** (I/O declarations as decomposition scaffolding), and **execution reasoning** (classification, contract checks, decision traces). Plus two safe effectors so colonies can produce outcomes, not just text.

---

## The Event-Sourcing Truth Problem

The most important design decision in this wave is **how artifacts survive replay.**

Current state:
- `AgentTurnCompleted.output_summary` stores only the first ~200 chars of agent output (runner.py line 885)
- `ColonyCompleted.summary` stores a compressed round summary (colony_manager.py line 573)
- Projections rebuild from events on startup. Any state not persisted in events is lost on restart.

This means artifacts cannot be reliable first-class outputs if they live only on the in-memory projection. On restart, the projection rebuilds from events and the full agent outputs that generated the artifacts are gone.

### Resolution: Additive Field on ColonyCompleted

0 new event types. Add one additive optional field to `ColonyCompleted`:

```python
class ColonyCompleted(EventEnvelope):
    # ... existing fields ...
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Final typed artifacts produced by the colony.",
    )
```

This is backward-compatible -- the default is an empty list. Existing serialized events without this field deserialize with `artifacts=[]`.

**Execution flow:**
1. **Live:** After each `run_round()`, the colony_manager has access to `result.outputs` (full agent outputs, `dict[str, str]`). Run artifact extraction on these full outputs. Accumulate on the projection for live consumers.
2. **Persist:** When the colony completes, the accumulated artifact list is serialized onto `ColonyCompleted.artifacts`. This is the source of truth.
3. **Replay:** `_on_colony_completed` handler restores `colony.artifacts` from the event. Final artifacts survive restart.

**Explicit limitation:** Per-round intermediate artifacts (accumulated during live execution) are NOT reconstructed on replay -- only the final artifact list from `ColonyCompleted` is persisted. This is acceptable because:
- External consumers (A2A, transcript) only need final artifacts
- Colony chaining only chains from completed colonies
- The Queen's follow-up only fires on completion
- Per-round artifacts are a live convenience, not a contract

---

## Tracks

### Track A -- Artifact Model + Task Contracts

**Goal:** Colony outputs become named, typed, provenance-carrying reasoning objects. Artifacts are replay-safe via `ColonyCompleted`. Templates describe what they take and produce. Transcripts and A2A expose artifacts as first-class results.

**A1. Core types: Artifact and ArtifactType.**

Add to `core/types.py`:

```python
class ArtifactType(StrEnum):
    code = "code"
    test = "test"
    document = "document"
    schema = "schema"
    data = "data"
    config = "config"
    report = "report"
    generic = "generic"

class Artifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable ID: art-{colony}-{agent}-r{round}-{n}")
    name: str = Field(description="Human-readable name, e.g. 'email_validator.py'")
    artifact_type: ArtifactType = Field(default=ArtifactType.generic)
    mime_type: str = Field(default="text/plain")
    content: str = Field(description="Artifact content")
    source_colony_id: str = Field(default="")
    source_agent_id: str = Field(default="")
    source_round: int = Field(default=0)
    created_at: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Files touched: `src/formicos/core/types.py` (~35 LOC)

**A2. Heuristic artifact extraction.**

New module `surface/artifact_extractor.py` (~100 LOC). Pure function: takes output string + colony/agent/round metadata, returns list of Artifact dicts.

Extraction rules (deterministic, not LLM-based):
- Fenced code block (` ```python ... ``` ` or similar) --> `code` artifact, language in metadata
- Fenced JSON block --> `data` or `schema` (schema if contains `"type"`, `"properties"`, or `"$schema"`)
- Fenced YAML block --> `config` artifact
- Content with markdown headers and substantial prose (>500 chars, >=2 headers) --> `document` artifact
- No structured blocks detected --> entire output is a single `generic` artifact

Each artifact gets a stable ID: `art-{colony_id}-{agent_id}-r{round}-{index}`.

Name defaults to `"output-{index}"` unless inferable from context. In Wave 25, `file_write` persists named deliverables to the workspace file surface, but artifact extraction itself still comes from colony outputs rather than a second tool-side artifact path.

Files touched: `src/formicos/surface/artifact_extractor.py` -- new (~100 LOC)

**A3. Artifact accumulation on projection + persistence on ColonyCompleted.**

Add to `ColonyProjection` in `projections.py`:
```python
artifacts: list[dict[str, Any]] = field(default_factory=list)
expected_output_types: list[str] = field(default_factory=list)
```

**Live accumulation:** In `colony_manager.py`, after each `run_round()` completes, call the artifact extractor on `result.outputs` (full agent outputs available in memory) and append to `colony_projection.artifacts`.

**Persistence:** When emitting `ColonyCompleted`, include the accumulated artifact list:
```python
await self._runtime.emit_and_broadcast(ColonyCompleted(
    seq=0, timestamp=_now(), address=address,
    colony_id=colony_id, summary=result.round_summary,
    skills_extracted=skills_count,
    artifacts=[a for a in colony_proj.artifacts],  # NEW
))
```

**Replay:** In `_on_colony_completed` handler, restore artifacts:
```python
def _on_colony_completed(store, event):
    e = event
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "completed"
        colony.skills_extracted = e.skills_extracted
        colony.artifacts = getattr(e, "artifacts", [])  # NEW - replay safe
```

**Additive field on ColonyCompleted** in `core/events.py`:
```python
class ColonyCompleted(EventEnvelope):
    # ... existing fields ...
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Final typed artifacts. Additive field (Wave 25).",
    )
```

Files touched:
- `src/formicos/core/events.py` -- additive artifacts field on ColonyCompleted (~3 LOC)
- `src/formicos/surface/projections.py` -- artifacts + expected_output_types fields, restore in handler (~10 LOC)
- `src/formicos/surface/colony_manager.py` -- extraction hook after rounds, serialize on completion (~30 LOC)

**A4. Task contracts on templates.**

Extend `ColonyTemplate` in `template_manager.py`:
```python
class ColonyTemplate(BaseModel):
    # ... existing fields ...
    input_description: str = ""
    output_description: str = ""
    expected_output_types: list[str] = []
    completion_hint: str = ""
```

Human-readable descriptions plus expected artifact types. Not JSON Schema. The Queen reads descriptions and reasons over them. `expected_output_types` feeds the contract satisfaction check (Track B).

Update all 7 built-in templates. Examples:

```yaml
# config/templates/code-review.yaml
input_description: "Code to review, or a task description for new code"
output_description: "Implementation code plus review feedback"
expected_output_types: ["code", "report"]
completion_hint: "Code is implemented and review feedback is provided"

# config/templates/research-heavy.yaml
input_description: "A research question or topic to investigate"
output_description: "Research summary document with findings and sources"
expected_output_types: ["document"]
completion_hint: "Research question is answered with supporting evidence"
```

Files touched:
- `src/formicos/surface/template_manager.py` -- add contract fields (~10 LOC)
- `config/templates/*.yaml` -- add contract fields to all 7 templates

**A5. Artifacts in transcript and A2A results.**

`build_transcript()` in `transcript.py` gains an `artifacts` field. Content is replaced with `preview` (first 500 chars) to keep payloads manageable:

```python
"artifacts": [
    {
        "id": "art-colony-abc-coder-001-r3-0",
        "name": "email_validator.py",
        "artifact_type": "code",
        "mime_type": "text/python",
        "preview": "def validate_email(addr: str) -> bool:\n    ...",
        "source_agent_id": "coder-001",
        "source_round": 3,
    },
]
```

A2A `GET /a2a/tasks/{id}/result` includes artifacts automatically since it calls `build_transcript()`.

Files touched: `src/formicos/surface/transcript.py` (~15 LOC)

**A6. Artifact-aware colony chaining.**

Today `InputSource` (core/types.py line 220) has only `summary: str`. Add an additive field:

```python
class InputSource(BaseModel):
    # ... existing fields ...
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Artifacts from the source colony (Wave 25).",
    )
```

In `runtime.py`, when resolving input_sources for a chained colony, include artifacts from the completed source colony's projection:

```python
resolved = {
    "colony_id": source_colony.id,
    "summary": _compress_summary(source_colony),
    "artifacts": source_colony.artifacts,  # restored from ColonyCompleted on replay
}
```

In `context.py` line 381, the input_sources injection includes artifact metadata alongside the summary:

```python
if artifacts:
    art_lines = [f"- {a['name']} ({a['artifact_type']}): {a.get('preview', '')[:200]}" for a in artifacts]
    parts.append("Artifacts produced:\n" + "\n".join(art_lines))
```

**Replay safety:** Chaining only operates on completed colonies. Completed colony artifacts are restored from `ColonyCompleted.artifacts` on replay. Therefore chaining is replay-safe.

Files touched:
- `src/formicos/core/types.py` -- additive artifacts field on InputSource (~3 LOC)
- `src/formicos/surface/runtime.py` -- include artifacts in resolved input_sources (~3 LOC)
- `src/formicos/engine/context.py` -- artifact-aware input_sources injection (~15 LOC)

---

### Track B -- Execution Reasoning

**Goal:** The Queen reasons about transformations, not just teams. Task classification feeds expected output types. Contract satisfaction provides a structured quality signal. Decision traces make reasoning inspectable. Classification logic is shared between Queen and A2A.

**B1. Shared task classifier.**

New module `surface/task_classifier.py` (~50 LOC). Both the Queen and A2A consume it. Classification does NOT live in `queen_runtime.py` -- that would create the wrong dependency direction.

```python
# src/formicos/surface/task_classifier.py

TASK_CATEGORIES: dict[str, dict[str, Any]] = {
    "code_implementation": {
        "keywords": {"implement", "write", "build", "create", "code", "function",
                     "script", "program", "develop", "fix", "debug"},
        "default_outputs": ["code", "test"],
        "default_rounds": 10,
    },
    "code_review": {
        "keywords": {"review", "audit", "check", "inspect", "evaluate"},
        "default_outputs": ["report"],
        "default_rounds": 5,
    },
    "research": {
        "keywords": {"research", "summarize", "analyze", "explain", "compare",
                     "investigate", "describe"},
        "default_outputs": ["document"],
        "default_rounds": 8,
    },
    "design": {
        "keywords": {"design", "architect", "plan", "schema", "api", "structure"},
        "default_outputs": ["schema", "document"],
        "default_rounds": 10,
    },
    "creative": {
        "keywords": {"haiku", "poem", "story", "essay", "translate"},
        "default_outputs": ["document"],
        "default_rounds": 3,
    },
}

def classify_task(description: str) -> tuple[str, dict[str, Any]]:
    words = set(description.lower().split())
    best_name = "generic"
    best_cat: dict[str, Any] = {"default_outputs": ["generic"], "default_rounds": 10}
    best_overlap = 0
    for name, cat in TASK_CATEGORIES.items():
        overlap = len(words & cat["keywords"])
        if overlap > best_overlap:
            best_name, best_cat, best_overlap = name, cat, overlap
    return best_name, best_cat
```

Deterministic keyword matching. The Queen's explicit choices (castes, rounds, budget) override these defaults. The classifier provides:
- Default expected output types when neither Queen nor template specifies them
- A classification label for the decision trace
- Shared logic consumed by both Queen and A2A

Files touched: `src/formicos/surface/task_classifier.py` -- new (~50 LOC)

**B2. Contract satisfaction check.**

On colony completion, check whether artifacts match expected output types:

```python
def check_contract(
    artifacts: list[dict[str, Any]],
    expected_types: list[str],
) -> dict[str, Any]:
    produced = [a.get("artifact_type", "generic") for a in artifacts]
    if not expected_types:
        return {"satisfied": True, "expected": [], "produced": produced, "missing": []}
    missing = [t for t in expected_types if t not in produced]
    return {
        "satisfied": len(missing) == 0,
        "expected": expected_types,
        "produced": produced,
        "missing": missing,
    }
```

Integrate into `follow_up_colony()`:
- "Contract satisfied: produced code, test"
- "Contract gap: expected code, test -- missing test"

Where do `expected_types` come from? Stored on `ColonyProjection.expected_output_types` at spawn time, sourced from either the template's `expected_output_types` or the classifier's `default_outputs`.

Files touched: `src/formicos/surface/queen_runtime.py` (~30 LOC)

**B3. Decision trace on spawn.**

Extend the spawn response with a structured decision record:

```
Colony abc123 spawned.
Classification: code_implementation
Template: builtin-code-review (matched by tags)
Team: coder(standard) + reviewer(standard)
Rounds: 10, Budget: $2.00, Strategy: stigmergic
Expected output: code, test
Related prior work: 2 hits from workspace memory
```

This extends the existing spawn response. Additions: classification label, template match explanation, expected output types.

Files touched: `src/formicos/surface/queen_runtime.py` (~15 LOC)

**B4. Decomposition guidance in Queen prompt.**

Extend the Queen prompt in `caste_recipes.yaml`:

```yaml
## Thinking in transformations
Every task is a transformation from inputs to typed outputs.
Before spawning, consider:
- What artifact types does this task need to produce? (code, document, schema, report, test)
- Does a template describe this transformation?
- Is this one transformation or a chain?

For complex tasks, decompose into a chain of transformations:
1. requirements -> schema (researcher)
2. schema -> implementation (coder + reviewer, input_from=step1)
3. implementation -> test suite (coder, input_from=step2)

Each step should have a clear output type. Use input_from to chain colonies.
When a colony completes, check: did it produce the expected artifact types?
```

Prompt guidance. The Queen decides whether to decompose. She now has vocabulary for typed transformations.

Files touched: `config/caste_recipes.yaml` (~20 lines)

**B5. A2A uses shared classifier.**

Replace the inline keyword heuristics in `routes/a2a.py` with the shared `classify_task()`:

```python
from formicos.surface.task_classifier import classify_task
category_name, category = classify_task(description)
```

One source of task-type truth. Queen and A2A classify identically.

Files touched: `src/formicos/surface/routes/a2a.py` (~net -10 LOC)

---

### Track C -- Safe Effectors (2 connectors)

**Goal:** Colonies can fetch data from the web and perform structured workspace file operations that produce artifacts. Policy-gated. Minimal surface. Reuses existing permission categories.

**C1. HTTP fetch tool.**

New agent tool `http_fetch` in runner.py:

```python
"http_fetch": {
    "name": "http_fetch",
    "description": "Fetch content from a URL. Returns text. Respects domain allowlist.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "max_bytes": {"type": "integer", "description": "Max response bytes (default 50000)"},
        },
        "required": ["url"],
    },
}
```

Implementation uses `httpx` (already a dependency). Gated by:
- **Domain allowlist** in `config/formicos.yaml` under `effectors.http_fetch.allowed_domains` -- default `["*"]`
- **Max response**: 50KB default, configurable
- **Timeout**: 10 seconds
- **Caste permissions**: uses existing `ToolCategory.network_out`. Add to coder and researcher policies.

Handler: validate URL against allowlist, fetch via `httpx.AsyncClient`, strip HTML tags for HTML responses (simple regex), truncate to max_bytes, return text.

**C2. Workspace file read/write tools.**

Two new agent tools for structured file interaction:

`file_read` -- reads a named file from the workspace library. Uses existing `ToolCategory.read_fs`. Available to all non-queen castes (already permitted for `read_fs`).

`file_write` -- writes a named file to the workspace. Uses existing `ToolCategory.write_fs`. Available to coder, researcher, archivist.

In Wave 25, `file_write` is a workspace effector, not a second artifact-persistence path. It lets colonies persist named deliverables into the same workspace file surface the operator already uses. Artifact truth remains concentrated in `ColonyCompleted.artifacts`.

Both tools operate on `{data_dir}/workspaces/{workspace_id}/files/` -- the same path as the existing workspace file surface. Extension whitelist and size caps match existing constraints.

**C3. Permission wiring.**

Reuse existing categories. No new ToolCategory entries needed:
- `http_fetch` --> `ToolCategory.network_out`
- `file_read` --> `ToolCategory.read_fs`
- `file_write` --> `ToolCategory.write_fs`

Add `network_out` to coder and researcher caste policies:
```python
"coder": CasteToolPolicy(
    caste="coder",
    allowed_categories=frozenset({
        ToolCategory.exec_code, ToolCategory.vector_query,
        ToolCategory.read_fs, ToolCategory.write_fs,
        ToolCategory.network_out,  # NEW
    }),
),
"researcher": CasteToolPolicy(
    caste="researcher",
    allowed_categories=frozenset({
        ToolCategory.vector_query, ToolCategory.search_web,
        ToolCategory.read_fs, ToolCategory.network_out,  # NEW
    }),
    denied_tools=frozenset({"code_execute"}),
),
```

Files touched:
- `src/formicos/engine/runner.py` -- tool specs, handlers, category mappings, policy updates (~90 LOC)
- `config/formicos.yaml` -- effector config section (~10 lines)

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|-----------------|--------------|
| **Coder 1** | A (Artifacts + Contracts) | `core/types.py`, `core/events.py`, `artifact_extractor.py`, `projections.py`, `colony_manager.py`, `template_manager.py`, `transcript.py`, `context.py`, `runtime.py` | None -- starts immediately |
| **Coder 2** | B (Execution Reasoning) | `task_classifier.py`, `queen_runtime.py`, `caste_recipes.yaml`, `routes/a2a.py` | Uses artifact types defined by Track A but does not modify Track A files |
| **Coder 3** | C (Effectors) | `runner.py`, `formicos.yaml` | No overlap with Tracks A or B |

### Serialization Rules

- **Coder 1 touches `core/types.py` and `core/events.py`** -- Artifact model and additive field on ColonyCompleted. Coder 3 does NOT touch these files.
- **Coder 2 creates `task_classifier.py`** as a new shared module. A2A imports from it after Coder 2 lands.
- **Coder 3 touches only `runner.py` and `formicos.yaml`** -- fully independent.

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `core/types.py` | 1 only | Artifact, ArtifactType, InputSource.artifacts |
| `core/events.py` | 1 only | ColonyCompleted.artifacts additive field |
| `runner.py` | 3 only | New tool specs, handlers, category mappings |
| `queen_runtime.py` | 2 only | Contract check, decision trace, classification integration |
| `routes/a2a.py` | 2 only | Import shared classifier |
| `colony_manager.py` | 1 only | Extraction hook, serialize on completion |
| All other files | Single-track | No overlap |

---

## Acceptance Criteria

1. **Colonies produce typed artifacts.** A code colony's transcript includes artifacts with type "code."
2. **Artifact extraction is heuristic and automatic.** Fenced code blocks become code artifacts. Prose becomes document artifacts.
3. **Completed colony artifacts survive restart.** After stopping and restarting FormicOS, `GET /a2a/tasks/{id}/result` for a previously completed colony returns its artifact list.
4. **Per-round artifacts are live-only.** The docs are honest: intermediate per-round artifacts are accumulated during live execution and lost on replay. Only final artifacts (from ColonyCompleted) are persisted.
5. **Templates have I/O descriptions.** All 7 built-in templates describe what they take and produce.
6. **Colony chaining passes artifact context.** Chained colonies see predecessor's artifacts with previews.
7. **Chaining is replay-safe.** Artifacts on completed colonies are restored from `ColonyCompleted` events, so chaining works correctly after restart.
8. **A2A results include artifact list.** External agents see typed output objects.
9. **Task classification is deterministic and shared.** `task_classifier.py` is consumed by both Queen and A2A.
10. **Contract satisfaction is checked on completion.** Queen follow-up says whether expected artifact types were produced.
11. **Decision trace is visible on spawn.** Classification, template match, expected outputs in spawn response.
12. **`http_fetch` works for researcher/coder.** Fetches URLs, returns text, respects allowlist.
13. **`file_write` writes named workspace deliverables.** Colonies can persist files into the workspace file surface without introducing a second artifact source of truth.
14. **Effector permissions use existing categories.** `network_out`, `read_fs`, `write_fs` -- no new ToolCategory entries.
15. **Full pytest suite green.** Frontend build green.

### Smoke Traces

1. **Artifact extraction:** Spawn code colony --> coder produces fenced Python --> transcript includes `{type: "code"}`
2. **Replay safety:** Complete a colony --> restart FormicOS --> query transcript --> artifacts are present
3. **Contract check:** Template expects `["code", "test"]` --> colony produces only code --> follow-up says "missing test"
4. **Chaining:** Colony A produces code --> Colony B chains from A --> B's context includes "Artifacts: output-0 (code)"
5. **A2A artifacts:** `POST /a2a/tasks` --> complete --> `GET /result` --> response includes `artifacts`
6. **Decision trace:** "write an email validator" --> spawn response includes "Classification: code_implementation, Expected: code, test"
7. **HTTP fetch:** Research colony calls `http_fetch` --> returns text content
8. **File write deliverable:** Coder calls `file_write("validator.py", code)` --> `validator.py` appears in the workspace file surface

---

## Not In Wave 25

| Item | Reason |
|------|--------|
| Full JSON Schema for template I/O | Human-readable descriptions + artifact types are enough |
| LLM-based artifact classification | Heuristic is deterministic and sufficient |
| Artifact storage service / CDN | Artifacts live on events + projections |
| Agent-navigable context (RLM Phase 2) | Current system-assembled context works; Wave 26+ |
| Recursive decomposition strategies | Needs artifact substrate first; Wave 27+ |
| Browser automation / DB connectors | Too complex for first effector wave |
| New ToolCategory entries | Existing categories cover all needs |
| RL on execution reasoning | Post-substrate |
| Workflow/runbook primitive | Emerges from artifacts + chaining; Wave 27+ |

---

## ADR Guidance

No standalone ADR is needed for this wave. The design choices are:
- **Additive field on ColonyCompleted:** This is a wave-level contract change documented here, not a deep architectural decision. It follows the same pattern as Wave 22 adding `failure_reason` / `killed_by` to projections via existing event data.
- **Artifact model:** A new core type, but not an architectural decision on the level of event sourcing, port design, or protocol choice.
- **Task classifier:** A shared helper module, not an architectural boundary.

No new ADR is required for Wave 25. The artifact-persistence choice is a wave-level contract change: additive fields on existing types/events, not a new architectural boundary.

---

## What This Enables Next

**Wave 26: Agent-Navigable Context.** Give agents tools to explore their environment: inspect artifact contents by ID, search across artifact metadata, request specific sections. Retrieval becomes pull-based ("agent requests what it needs") rather than push-based ("system stuffs the window"). This is the RLM "context as environment" move.

**Wave 27: Service Contracts + Composition.** Services declare typed capabilities (input types --> output types). The Queen routes by matching type signatures. Sequential pipeline primitives let operators describe transformation chains as YAML runbooks.

**Wave 28: Learned Decomposition.** The evaluation harness measures contract satisfaction, artifact quality, and decomposition effectiveness. That data tells you whether the Queen's classification is accurate, whether templates are well-matched, and where decomposition breaks down -- the foundation for RL on execution reasoning quality.
