# Wave 25 Algorithms -- Implementation Reference

**Wave:** 25 -- "Typed Transformations"
**Purpose:** Technical implementation guide for all three tracks.

---

## S1. Artifact and ArtifactType (Track A -- A1)

### New Types in core/types.py

```python
from enum import StrEnum

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
    name: str = Field(description="Human-readable name")
    artifact_type: ArtifactType = Field(default=ArtifactType.generic)
    mime_type: str = Field(default="text/plain")
    content: str = Field(description="Artifact content")
    source_colony_id: str = Field(default="")
    source_agent_id: str = Field(default="")
    source_round: int = Field(default=0)
    created_at: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Additive Field on InputSource

```python
class InputSource(BaseModel):
    # ... existing fields ...
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Artifacts from the completed source colony (Wave 25).",
    )
```

---

## S2. Additive Field on ColonyCompleted (Track A -- A3)

### Event Change in core/events.py

```python
class ColonyCompleted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyCompleted"] = "ColonyCompleted"
    colony_id: str = Field(..., description="Completed colony identifier.")
    summary: str = Field(..., description="Compressed final outcome summary.")
    skills_extracted: int = Field(..., ge=0, description="Number of skill records extracted.")
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Final typed artifacts produced by the colony (Wave 25 additive field).",
    )
```

Backward compatible: existing serialized events without `artifacts` deserialize with `[]`.

### Projection Restore in projections.py

```python
def _on_colony_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyCompleted = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "completed"
        colony.skills_extracted = e.skills_extracted
        colony.artifacts = getattr(e, "artifacts", [])  # Wave 25: replay-safe
```

---

## S3. Heuristic Artifact Extractor (Track A -- A2)

### Module: surface/artifact_extractor.py

```python
"""Heuristic artifact extraction from agent output text.

Deterministic, not LLM-based. Called after each round on full agent outputs.
Extracted artifacts accumulate on the colony projection during live execution
and are persisted on ColonyCompleted for replay safety.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from formicos.core.types import Artifact, ArtifactType

# Regex for fenced code blocks: ```lang\n...\n```
_FENCED_RE = re.compile(
    r"```(\w*)\s*\n(.*?)```",
    re.DOTALL,
)

# Language hint -> artifact type
_LANG_TYPE: dict[str, ArtifactType] = {
    "python": ArtifactType.code,
    "py": ArtifactType.code,
    "javascript": ArtifactType.code,
    "js": ArtifactType.code,
    "typescript": ArtifactType.code,
    "ts": ArtifactType.code,
    "rust": ArtifactType.code,
    "go": ArtifactType.code,
    "java": ArtifactType.code,
    "json": ArtifactType.data,
    "yaml": ArtifactType.config,
    "yml": ArtifactType.config,
    "sql": ArtifactType.code,
    "html": ArtifactType.code,
    "css": ArtifactType.code,
    "sh": ArtifactType.code,
    "bash": ArtifactType.code,
}

_LANG_MIME: dict[str, str] = {
    "python": "text/x-python",
    "py": "text/x-python",
    "javascript": "text/javascript",
    "js": "text/javascript",
    "typescript": "text/typescript",
    "ts": "text/typescript",
    "json": "application/json",
    "yaml": "text/yaml",
    "yml": "text/yaml",
    "html": "text/html",
    "css": "text/css",
    "sql": "text/x-sql",
}

_SCHEMA_HINTS = {"$schema", '"type"', '"properties"', "'type'", "'properties'"}


def extract_artifacts(
    output: str,
    colony_id: str,
    agent_id: str,
    round_number: int,
) -> list[dict[str, Any]]:
    """Extract typed artifacts from agent output text.

    Returns a list of artifact dicts (serialized Artifact shape).
    Deterministic: fenced blocks become typed artifacts, remaining prose
    becomes a document artifact if substantial.
    """
    artifacts: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    # Extract fenced code blocks
    fenced_spans: list[tuple[int, int]] = []
    for i, match in enumerate(_FENCED_RE.finditer(output)):
        lang = match.group(1).lower().strip()
        content = match.group(2).strip()
        fenced_spans.append((match.start(), match.end()))

        if not content:
            continue

        # Determine type
        art_type = _LANG_TYPE.get(lang, ArtifactType.code if lang else ArtifactType.generic)

        # Check if JSON content looks like a schema
        if art_type == ArtifactType.data:
            if any(hint in content[:500] for hint in _SCHEMA_HINTS):
                art_type = ArtifactType.schema

        mime = _LANG_MIME.get(lang, "text/plain")
        art_id = f"art-{colony_id}-{agent_id}-r{round_number}-{len(artifacts)}"

        artifacts.append(Artifact(
            id=art_id,
            name=f"output-{len(artifacts)}",
            artifact_type=art_type,
            mime_type=mime,
            content=content,
            source_colony_id=colony_id,
            source_agent_id=agent_id,
            source_round=round_number,
            created_at=now,
            metadata={"language": lang} if lang else {},
        ).model_dump())

    # If no fenced blocks, check if output is a substantial document
    if not artifacts:
        header_count = len(re.findall(r"^#{1,3}\s+", output, re.MULTILINE))
        if len(output) > 500 and header_count >= 2:
            art_type = ArtifactType.document
        else:
            art_type = ArtifactType.generic

        art_id = f"art-{colony_id}-{agent_id}-r{round_number}-0"
        artifacts.append(Artifact(
            id=art_id,
            name="output-0",
            artifact_type=art_type,
            mime_type="text/plain",
            content=output,
            source_colony_id=colony_id,
            source_agent_id=agent_id,
            source_round=round_number,
            created_at=now,
        ).model_dump())

    return artifacts
```

---

## S4. Artifact Accumulation + Persistence in colony_manager.py (Track A -- A3)

### After Each Round

In the colony execution loop, after `result = await runner.run_round(...)` and after round projection updates, extract artifacts from full outputs:

```python
from formicos.surface.artifact_extractor import extract_artifacts

# After run_round returns and round is recorded:
for agent_id, agent_output in result.outputs.items():
    if agent_output:
        new_arts = extract_artifacts(
            output=agent_output,
            colony_id=colony_id,
            agent_id=agent_id,
            round_number=round_num,
        )
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None:
            colony_proj.artifacts.extend(new_arts)
```

### On Colony Completion

When emitting `ColonyCompleted`, include accumulated artifacts:

```python
colony_proj = self._runtime.projections.get_colony(colony_id)
final_artifacts = colony_proj.artifacts if colony_proj else []

await self._runtime.emit_and_broadcast(ColonyCompleted(
    seq=0, timestamp=_now(), address=address,
    colony_id=colony_id,
    summary=result.round_summary,
    skills_extracted=skills_count,
    artifacts=final_artifacts,
))
```

---

## S5. Task Contracts on Templates (Track A -- A4)

### Template Model Extension

```python
class ColonyTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ... existing fields ...
    input_description: str = ""
    output_description: str = ""
    expected_output_types: list[str] = []
    completion_hint: str = ""
```

### Template YAML Examples

```yaml
# code-review.yaml
input_description: "Code to review, or a task description for new code"
output_description: "Implementation code plus review feedback"
expected_output_types: ["code", "report"]
completion_hint: "Code is implemented and review feedback is provided"

# research-heavy.yaml
input_description: "A research question or topic to investigate"
output_description: "Research summary document with findings and sources"
expected_output_types: ["document"]
completion_hint: "Research question is answered with supporting evidence"

# debugging.yaml
input_description: "Bug report or failing test case"
output_description: "Fix with explanation and updated tests"
expected_output_types: ["code", "test"]
completion_hint: "Bug is fixed and tests pass"

# documentation.yaml
input_description: "Code or system to document"
output_description: "Documentation covering usage and architecture"
expected_output_types: ["document"]
completion_hint: "Documentation is comprehensive and accurate"

# full-stack.yaml
input_description: "Feature specification or requirements"
output_description: "Full implementation with tests and documentation"
expected_output_types: ["code", "test", "document"]
completion_hint: "Feature is implemented, tested, and documented"

# minimal.yaml
input_description: "Simple task or question"
output_description: "Direct answer or small output"
expected_output_types: ["generic"]
completion_hint: "Task is completed"

# rapid-prototype.yaml
input_description: "Feature idea or concept to prototype"
output_description: "Working prototype code"
expected_output_types: ["code"]
completion_hint: "Prototype demonstrates the concept"
```

---

## S6. Artifacts in Transcript + A2A (Track A -- A5)

### Transcript Extension

In `build_transcript()`, add artifacts with previews:

```python
def build_transcript(colony: ColonyProjection) -> dict[str, Any]:
    # ... existing code ...
    result = { ... }

    # Artifacts (Wave 25)
    if colony.artifacts:
        result["artifacts"] = [
            {
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "artifact_type": a.get("artifact_type", "generic"),
                "mime_type": a.get("mime_type", "text/plain"),
                "preview": a.get("content", "")[:500],
                "source_agent_id": a.get("source_agent_id", ""),
                "source_round": a.get("source_round", 0),
            }
            for a in colony.artifacts
        ]

    return result
```

A2A `GET /a2a/tasks/{id}/result` inherits artifacts automatically since it calls `build_transcript()`.

---

## S7. Artifact-Aware Colony Chaining (Track A -- A6)

### Runtime: Include Artifacts in Resolved Sources

In `runtime.py`, where input_sources are resolved for a chained colony:

```python
resolved = {
    "colony_id": source_colony.id,
    "summary": _compress_summary(source_colony),
    "artifacts": source_colony.artifacts,  # Wave 25
}
```

### Context Assembly: Inject Artifact Metadata

In `context.py`, replace the input_sources loop:

```python
if input_sources:
    for src in input_sources:
        summary = src.get("summary", "")
        artifacts = src.get("artifacts", [])
        parts: list[str] = []
        if summary:
            parts.append(f"Summary: {summary}")
        if artifacts:
            art_lines = [
                f"- {a.get('name', '?')} ({a.get('artifact_type', 'generic')}): "
                f"{a.get('content', a.get('preview', ''))[:200]}"
                for a in artifacts
            ]
            parts.append("Artifacts produced:\n" + "\n".join(art_lines))
        if parts:
            source_id = src.get("colony_id", "unknown")
            src_text = _truncate(
                f"[Context from prior colony {source_id}]:\n" + "\n".join(parts),
                budgets.max_per_source,
            )
            messages.append({"role": "user", "content": src_text})
```

---

## S8. Shared Task Classifier (Track B -- B1)

### Module: surface/task_classifier.py

```python
"""Shared deterministic task classifier.

Consumed by Queen (queen_runtime.py) and A2A (routes/a2a.py).
Does NOT live in queen_runtime.py to avoid wrong dependency direction.
"""

from __future__ import annotations
from typing import Any

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

_GENERIC_CATEGORY: dict[str, Any] = {
    "default_outputs": ["generic"],
    "default_rounds": 10,
}


def classify_task(description: str) -> tuple[str, dict[str, Any]]:
    """Classify a task by keyword matching. Returns (category_name, category_dict)."""
    words = set(description.lower().split())
    best_name = "generic"
    best_cat = _GENERIC_CATEGORY
    best_overlap = 0
    for name, cat in TASK_CATEGORIES.items():
        overlap = len(words & cat["keywords"])
        if overlap > best_overlap:
            best_name, best_cat, best_overlap = name, cat, overlap
    return best_name, best_cat
```

---

## S9. Contract Satisfaction + Decision Trace (Track B -- B2/B3)

### Contract Check

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

### Integration in queen_runtime.py

**On spawn** (in `_tool_spawn_colony`):

```python
from formicos.surface.task_classifier import classify_task

cat_name, cat = classify_task(task)

# Expected types: template > classifier > empty
if template and template.expected_output_types:
    expected = template.expected_output_types
else:
    expected = cat.get("default_outputs", [])

# Store on projection
colony_proj = self._runtime.projections.get_colony(colony_id)
if colony_proj:
    colony_proj.expected_output_types = expected

# Decision trace in spawn response
trace_lines = [
    f"Colony {colony_id} spawned.",
    f"Classification: {cat_name}",
]
if template:
    trace_lines.append(f"Template: {template.template_id} (matched)")
trace_lines.append(f"Team: {team_desc}")
trace_lines.append(f"Rounds: {max_rounds}, Budget: ${budget_limit:.2f}, Strategy: {strategy}")
if expected:
    trace_lines.append(f"Expected output: {', '.join(expected)}")
# ... existing prior work lines ...

spawn_msg = "\n".join(trace_lines)
```

**On follow-up** (in `follow_up_colony`):

```python
# After existing quality branching:
contract = check_contract(colony.artifacts, colony.expected_output_types)
if contract["satisfied"] and contract["expected"]:
    summary += f"\nContract satisfied: produced {', '.join(contract['produced'])}."
elif contract["missing"]:
    summary += f"\nContract gap: expected {', '.join(contract['expected'])}, missing {', '.join(contract['missing'])}."
```

---

## S10. Effector Tools (Track C)

### http_fetch Tool Spec

```python
TOOL_SPECS["http_fetch"] = {
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

TOOL_CATEGORY_MAP["http_fetch"] = ToolCategory.network_out
```

### http_fetch Handler

```python
async def _handle_http_fetch(arguments: dict[str, Any], settings: SystemSettings) -> str:
    url = arguments.get("url", "")
    max_bytes = int(arguments.get("max_bytes", 50000))

    # Domain allowlist
    allowed = getattr(settings, "http_fetch_allowed_domains", ["*"])
    if "*" not in allowed:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
        if not any(domain.endswith(d) for d in allowed):
            return f"Error: domain {domain} not in allowlist"

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text[:max_bytes]
            # Strip HTML tags if HTML content
            if "html" in resp.headers.get("content-type", "").lower():
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()
            return content
    except Exception as e:
        return f"Error fetching {url}: {e}"
```

### file_read / file_write Tool Specs

```python
TOOL_SPECS["file_read"] = {
    "name": "file_read",
    "description": "Read a file from the workspace library by name.",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "File name to read"},
        },
        "required": ["filename"],
    },
}
TOOL_CATEGORY_MAP["file_read"] = ToolCategory.read_fs

TOOL_SPECS["file_write"] = {
    "name": "file_write",
    "description": "Write a named file to the workspace. Creates a colony artifact.",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "File name, e.g. 'output.py'"},
            "content": {"type": "string", "description": "File content"},
        },
        "required": ["filename", "content"],
    },
}
TOOL_CATEGORY_MAP["file_write"] = ToolCategory.write_fs
```

### file_write Handler

```python
async def _handle_file_write(
    arguments: dict[str, Any],
    workspace_id: str,
    data_dir: str,
) -> str:
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")

    # Extension whitelist
    ext = Path(filename).suffix.lower()
    ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml",
                          ".html", ".css", ".sql", ".csv", ".toml", ".sh", ".rs", ".go"}
    if ext not in ALLOWED_EXTENSIONS:
        return f"Error: extension {ext} not allowed"
    if len(content) > 50_000:
        return "Error: content exceeds 50KB limit"

    # Write file
    ws_dir = Path(data_dir) / "workspaces" / workspace_id / "files"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / filename).write_text(content, encoding="utf-8")
    return f"Wrote {filename} ({len(content)} chars) to workspace files."
```

Wave 25 keeps this intentionally narrow:
- the current runner tool interface is string-returning
- Track A already establishes a single artifact-truth path via `ColonyCompleted.artifacts`
- `file_write` is therefore a workspace effector, not a second artifact-persistence mechanism

### Caste Permission Updates

```python
"coder": CasteToolPolicy(
    caste="coder",
    allowed_categories=frozenset({
        ToolCategory.exec_code, ToolCategory.vector_query,
        ToolCategory.read_fs, ToolCategory.write_fs,
        ToolCategory.network_out,  # Wave 25
    }),
),
"researcher": CasteToolPolicy(
    caste="researcher",
    allowed_categories=frozenset({
        ToolCategory.vector_query, ToolCategory.search_web,
        ToolCategory.read_fs,
        ToolCategory.network_out,  # Wave 25
    }),
    denied_tools=frozenset({"code_execute"}),
),
```

---

## S11. Config Extension for Effectors (Track C)

### formicos.yaml Addition

```yaml
# Effector configuration (Wave 25)
effectors:
  http_fetch:
    allowed_domains: ["*"]    # ["*"] for open, or list of specific domains
    max_bytes: 50000
    timeout_seconds: 10
```

---

## S12. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | Artifact, ArtifactType, InputSource.artifacts (~35 LOC) |
| `src/formicos/core/events.py` | Additive `artifacts` field on ColonyCompleted (~3 LOC) |
| `src/formicos/surface/artifact_extractor.py` | New -- heuristic extraction (~100 LOC) |
| `src/formicos/surface/projections.py` | artifacts + expected_output_types fields, restore in handler (~10 LOC) |
| `src/formicos/surface/colony_manager.py` | Extraction hook after rounds, serialize artifacts on completion (~30 LOC) |
| `src/formicos/surface/template_manager.py` | Contract fields on ColonyTemplate (~10 LOC) |
| `src/formicos/surface/transcript.py` | Artifacts in output (~15 LOC) |
| `src/formicos/surface/runtime.py` | Include artifacts in resolved input_sources (~3 LOC) |
| `src/formicos/engine/context.py` | Artifact-aware input_sources injection (~15 LOC) |
| `config/templates/*.yaml` | Add contract fields to all 7 templates |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/surface/task_classifier.py` | New -- shared classifier (~50 LOC) |
| `src/formicos/surface/queen_runtime.py` | Classification integration, contract check, decision trace (~60 LOC) |
| `config/caste_recipes.yaml` | Transformation/decomposition prompt guidance (~20 lines) |
| `src/formicos/surface/routes/a2a.py` | Import shared classifier, remove inline heuristics (~net -10 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/engine/runner.py` | Tool specs, handlers, category mappings, policy updates (~90 LOC) |
| `config/formicos.yaml` | Effector config section (~10 lines) |
