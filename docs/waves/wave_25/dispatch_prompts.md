# Wave 25 Dispatch Prompts

Three parallel coder teams. Each prompt is self-contained.

---

## Team 1 -- Track A: Artifact Model + Task Contracts

```
You are Coder 1 for Wave 25. Your track is "Artifact Model + Task Contracts."
This is the heart of the wave: making colony outputs typed, named, replay-safe reasoning objects.

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_25\plan.md (Track A section + Event-Sourcing Truth section)
4. C:\Users\User\FormicOSa\docs\waves\wave_25\algorithms.md (S1-S7)

CRITICAL DESIGN CONSTRAINT -- READ CAREFULLY:
Artifacts must survive restart. The event-sourcing truth problem is real:
- AgentTurnCompleted.output_summary stores only ~200 chars (runner.py line 885)
- Projections rebuild from events on startup
- If artifacts only live on the projection, they vanish on restart

THE SOLUTION (documented in plan.md):
- Add an additive optional field "artifacts: list[dict[str, Any]]" to ColonyCompleted in core/events.py
- Default: empty list (backward compatible)
- Live: extract artifacts per-round from full agent outputs via result.outputs
- Persist: serialize accumulated artifacts on ColonyCompleted when colony finishes
- Replay: _on_colony_completed restores artifacts from the event
- Per-round artifacts are live-only (acceptable). Final artifacts are persistent (required).

Your deliverables:

A1. Core types
- Add ArtifactType (StrEnum) and Artifact (BaseModel) to core/types.py
- Add additive "artifacts: list[dict[str, Any]]" field to InputSource (default_factory=list)

A2. Heuristic artifact extraction
- Create src/formicos/surface/artifact_extractor.py (~100 LOC)
- Pure function: extract_artifacts(output, colony_id, agent_id, round_number) -> list[dict]
- Fenced code blocks -> code artifacts (with language metadata)
- Fenced JSON -> data or schema artifact
- Fenced YAML -> config artifact
- Prose with headers -> document artifact
- Fallback -> generic artifact
- Each artifact gets stable ID: art-{colony_id}-{agent_id}-r{round}-{index}
- Deterministic. No LLM calls.

A3. Projection fields + ColonyCompleted additive field + persistence hook
- Add "artifacts: list[dict[str, Any]] = field(default_factory=list)" to ColonyProjection
- Add "expected_output_types: list[str] = field(default_factory=list)" to ColonyProjection
- Add "artifacts: list[dict[str, Any]] = Field(default_factory=list)" to ColonyCompleted in core/events.py
- In _on_colony_completed handler: restore colony.artifacts from getattr(e, "artifacts", [])
- In colony_manager.py: after each run_round(), call extract_artifacts on result.outputs and append to projection
- In colony_manager.py: when emitting ColonyCompleted, include colony_proj.artifacts
- IMPORTANT: result.outputs (dict[str, str]) has full agent outputs in memory. Extract from there, not from AgentTurnCompleted.output_summary.

A4. Task contracts on templates
- Add input_description, output_description, expected_output_types, completion_hint to ColonyTemplate
- All optional with empty defaults (backward compatible)
- Update all 7 config/templates/*.yaml with contract fields

A5. Artifacts in transcript
- In build_transcript(): add "artifacts" field with previews (content[:500])
- A2A results inherit automatically

A6. Artifact-aware colony chaining
- In runtime.py: include colony.artifacts in resolved input_sources
- In context.py: inject artifact metadata alongside summary in input_sources loop
- Chaining only operates on completed colonies, whose artifacts are restored from ColonyCompleted

Key constraints:
- 0 new event TYPES. 1 additive field on existing ColonyCompleted.
- Artifacts are list[dict[str, Any]] in events (not list[Artifact]) for serialization simplicity
- Per-round artifacts are live convenience. Only final artifacts on ColonyCompleted are the truth.
- Colony chaining is replay-safe because completed colony artifacts restore from events.
- Keep artifact extraction conservative. Don't try to be clever with filenames.

Files you own:
- src/formicos/core/types.py (Artifact, ArtifactType, InputSource.artifacts)
- src/formicos/core/events.py (ColonyCompleted.artifacts additive field)
- src/formicos/surface/artifact_extractor.py (new)
- src/formicos/surface/projections.py (fields + restore handler)
- src/formicos/surface/colony_manager.py (extraction hook + serialize on completion)
- src/formicos/surface/template_manager.py (contract fields)
- src/formicos/surface/transcript.py (artifacts in output)
- src/formicos/surface/runtime.py (artifacts in resolved input_sources)
- src/formicos/engine/context.py (artifact-aware chaining injection)
- config/templates/*.yaml (all 7 templates)

Do not touch:
- src/formicos/engine/runner.py (owned by Coder 3)
- src/formicos/surface/queen_runtime.py (owned by Coder 2)
- src/formicos/surface/routes/a2a.py (owned by Coder 2)
- src/formicos/surface/task_classifier.py (owned by Coder 2)
- config/caste_recipes.yaml (owned by Coder 2)
- config/formicos.yaml (owned by Coder 3)
- frontend/ (no frontend changes in this wave)

Run full CI before declaring done:
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Team 2 -- Track B: Execution Reasoning

```
You are Coder 2 for Wave 25. Your track is "Execution Reasoning."
This track makes the Queen reason about transformations, not just teams.

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_25\plan.md (Track B section)
4. C:\Users\User\FormicOSa\docs\waves\wave_25\algorithms.md (S8-S9)

Your deliverables:

B1. Shared task classifier
- Create src/formicos/surface/task_classifier.py (~50 LOC)
- classify_task(description) -> (category_name, category_dict)
- Deterministic keyword matching against 5 categories: code_implementation, code_review, research, design, creative
- Fallback: "generic" with default_outputs=["generic"], default_rounds=10
- IMPORTANT: This does NOT live in queen_runtime.py. It is a shared module consumed by Queen and A2A.

B2. Contract satisfaction check
- In queen_runtime.py: add check_contract(artifacts, expected_types) -> dict
- Integrate into follow_up_colony():
  - "Contract satisfied: produced code, test"
  - "Contract gap: expected code, test -- missing test"
- expected_output_types come from colony.expected_output_types on the projection
  (set at spawn time from template or classifier defaults)

B3. Decision trace on spawn
- In queen_runtime.py _tool_spawn_colony():
  - Import classify_task from task_classifier
  - Classify the task
  - Source expected_output_types: template.expected_output_types if template, else classifier defaults
  - Store expected_output_types on the colony projection
  - Build decision trace: classification, template match, team, rounds/budget, expected outputs
  - Include trace in spawn response message

B4. Decomposition guidance in Queen prompt
- In config/caste_recipes.yaml: add "Thinking in transformations" section
- Guide the Queen to think about output types, template matching, and chaining
- Prompt guidance, not new tools

B5. A2A uses shared classifier
- In routes/a2a.py: replace inline keyword heuristics with:
  from formicos.surface.task_classifier import classify_task
- Remove the inline _CODE_KEYWORDS, _REVIEW_KEYWORDS, _RESEARCH_KEYWORDS, _select_team duplicate logic
- Use classifier defaults for team selection when no template matches

Key constraints:
- Task classifier is a shared module, not Queen-owned logic
- Classification is deterministic keyword matching, not LLM-based
- Queen's explicit choices override classifier defaults
- contract check reads artifacts from the colony projection (Track A populates these)
- If Track A hasn't landed yet, contract check gracefully handles empty artifact lists

Files you own:
- src/formicos/surface/task_classifier.py (new)
- src/formicos/surface/queen_runtime.py (classification, contract check, decision trace)
- config/caste_recipes.yaml (prompt additions)
- src/formicos/surface/routes/a2a.py (import shared classifier, remove inline heuristics)

Do not touch:
- src/formicos/core/ (any file -- owned by Coder 1)
- src/formicos/engine/ (any file -- owned by Coder 3)
- src/formicos/surface/projections.py (owned by Coder 1)
- src/formicos/surface/colony_manager.py (owned by Coder 1)
- src/formicos/surface/template_manager.py (owned by Coder 1)
- src/formicos/surface/transcript.py (owned by Coder 1)
- config/formicos.yaml (owned by Coder 3)
- config/templates/ (owned by Coder 1)
- frontend/ (no frontend changes)

Run full CI before declaring done:
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Team 3 -- Track C: Safe Effectors

```
You are Coder 3 for Wave 25. Your track is "Safe Effectors."
Two new agent tools: HTTP fetch and workspace file read/write. Minimal. Policy-gated.

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_25\plan.md (Track C section)
4. C:\Users\User\FormicOSa\docs\waves\wave_25\algorithms.md (S10-S11)

Your deliverables:

C1. HTTP fetch tool
- Add "http_fetch" to TOOL_SPECS in runner.py
- Map to ToolCategory.network_out in TOOL_CATEGORY_MAP (already exists in core/types.py)
- Handler: validate URL against domain allowlist, fetch via httpx.AsyncClient, strip HTML tags for HTML content, truncate to max_bytes, return text
- Domain allowlist from config: effectors.http_fetch.allowed_domains (default ["*"])
- Max response: 50KB default
- Timeout: 10 seconds
- httpx is already a project dependency

C2. Workspace file read/write tools
- Add "file_read" and "file_write" to TOOL_SPECS
- file_read maps to ToolCategory.read_fs (already exists)
- file_write maps to ToolCategory.write_fs (already exists)
- file_read handler: read from {data_dir}/workspaces/{workspace_id}/files/{filename}
- file_write handler: write to same path. Extension whitelist + 50KB cap.
- IMPORTANT: file_write does NOT directly modify the colony projection. It writes the file to disk and returns a confirmation string.

C3. Caste permission updates
- Add ToolCategory.network_out to coder and researcher CASTE_TOOL_POLICIES
- file_read uses read_fs (coder, reviewer, researcher, archivist already have this)
- file_write uses write_fs (coder already has this; add to researcher and archivist if not present)
- Do NOT add new ToolCategory entries. Reuse existing: network_out, read_fs, write_fs.

C4. Effector config
- Add effectors section to config/formicos.yaml:
  effectors:
    http_fetch:
      allowed_domains: ["*"]
      max_bytes: 50000
      timeout_seconds: 10
- Read these values in the http_fetch handler from the settings object

Key constraints:
- Only 2 connectors: http_fetch and file_read/file_write. Nothing else.
- Reuse existing ToolCategory entries. No new categories.
- file_write creates files on disk. Artifact truth remains Track A's responsibility through ColonyCompleted.artifacts.
- The handler signatures must match the existing pattern in runner.py _execute_tool()
- Check how existing tools receive arguments (workspace_id, colony_id, etc.)

Files you own:
- src/formicos/engine/runner.py (tool specs, handlers, category mappings, policies)
- config/formicos.yaml (effector config section only)

Do not touch:
- src/formicos/core/ (any file -- owned by Coder 1)
- src/formicos/surface/ (any file -- owned by Coders 1 and 2)
- config/templates/ (owned by Coder 1)
- config/caste_recipes.yaml (owned by Coder 2)
- frontend/ (no frontend changes)

Run full CI before declaring done:
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
