# Wave 22 Algorithms - Implementation Reference

**Wave:** 22 - "Trust the Product"  
**Purpose:** Technical implementation guide for the three Wave 22 tracks, written against the actual post-Wave-21 repo structure.

---

## 1. Queen Spawn Controls

### Current state

The Queen's `spawn_colony` tool still underexposes runtime controls even though `runtime.spawn_colony()` already supports them.

Wave 22 should expose and pass through:

- `max_rounds`
- `budget_limit`
- `template_id`
- `strategy`

### Tool-definition shape

Suggested additions:

```python
"max_rounds": {
    "type": "integer",
    "description": "Maximum rounds. Trivial: 2-4. Moderate: 5-10. Complex: 10-25.",
},
"budget_limit": {
    "type": "number",
    "description": "Budget cap in dollars. Keep trivial tasks low.",
},
"template_id": {
    "type": "string",
    "description": "Template ID from list_templates when a template fits.",
},
"strategy": {
    "type": "string",
    "enum": ["stigmergic", "sequential"],
    "description": "Use sequential for simple tasks, stigmergic for multi-agent work.",
},
```

### Handler pass-through

Suggested shape:

```python
max_rounds = max(1, min(int(inputs.get("max_rounds", 25)), 50))
budget_limit = max(0.01, min(float(inputs.get("budget_limit", 5.0)), 50.0))
template_id = str(inputs.get("template_id", ""))
strategy = str(inputs.get("strategy", "stigmergic"))

colony_id = await self._runtime.spawn_colony(
    workspace_id,
    thread_id,
    task,
    caste_slots,
    strategy=strategy,
    max_rounds=max_rounds,
    budget_limit=budget_limit,
    template_id=template_id,
    input_sources=input_sources,
)
```

This is the direct fix for trivial tasks inheriting heavyweight defaults.

---

## 2. Queen Prompt Rewrite

### Intent

The Queen prompt should teach better judgment, not just list tools.

### Required prompt content

- full live tool surface
- team-composition heuristics
- trivial/moderate/complex resource heuristics
- template-first behavior
- concise, action-first interaction style

### Required heuristics

- non-code tasks -> researcher, not coder
- code implementation -> coder + reviewer
- code review -> reviewer first
- trivial tasks -> sequential, low round count
- templates should be checked before building teams from scratch

### Recipe updates

Update:

- Queen `system_prompt`
- Queen `tools` list

And make sure the recipe-level max-iteration guidance matches the live `_MAX_TOOL_ITERATIONS = 7` baseline.

---

## 3. AG-UI Default Team

### Current state

The AG-UI endpoint still defaults to a single coder when `castes` is omitted.

### Wave 22 fix

Raise the floor:

```python
castes = [
    CasteSlot(caste="coder", tier="standard"),
    CasteSlot(caste="reviewer", tier="standard"),
]
```

This is only a default-path change. Explicit caller-supplied castes still win.

---

## 4. Scoped Colony Scratch Memory

### Decision

Wave 22 should adopt:

- `scratch_{colony_id}` for colony-private scratch writes

and keep reads layered:

- colony scratch
- workspace memory
- skill bank

This decision should live in:

- `docs/decisions/037-scoped-colony-memory.md`

### Write path

Change `memory_write` from:

```python
collection=workspace_id
```

to:

```python
collection=f"scratch_{colony_id}"
```

### Read path

Search in this order:

```python
for collection in (f"scratch_{colony_id}", workspace_id, skill_coll):
    ...
```

### Important implementation note

If `_handle_memory_search()` does not currently receive `colony_id`, thread it through from the tool-execution path. This is part of the Wave 22 scoped-memory change.

### Why this is enough

No VectorPort API change is needed. The collection parameter already gives enough separation for this wave.

---

## 5. Queen Memory Search Scope

The Queen should keep searching:

- workspace memory
- skill bank

and should not search colony-private scratch collections by default.

This is both a product decision and a trust decision:

- colonies get private scratchpads
- the Queen sees shared knowledge

Update the Queen tool description if necessary so this scope is explicit.

---

## 6. Knowledge Ingestion Path

### Goal

Make workspace documents explicitly ingestable into searchable workspace memory.

### Backend shape

Extend the workspace file upload path with an explicit ingest flag or explicit library-ingest route.

Important repo-shaped note:

- the route module already exists in `src/formicos/surface/routes/colony_io.py`
- it already has access to `runtime`, so it can use `runtime.vector_store`

### Ingestion behavior

After file write:

- read text
- chunk it
- create `VectorDocument`s
- upsert into workspace memory collection

Suggested metadata:

- `source_file`
- `chunk_index`
- `type: "workspace_doc"`
- `workspace_id`
- `ingested_at`

### Frontend shape

Add a `library` tab to `knowledge-view.ts`.

That tab should:

- show workspace-library docs/files
- offer upload + ingest
- make it clear that this path adds searchable knowledge

### Important rule

Only the explicit Knowledge Library path should embed. Normal workspace-file upload should remain file storage only.

---

## 7. Colony vs Workspace File Scope

The colony detail UI should distinguish between:

- colony-specific uploads
- workspace-shared library files

This is mostly presentation work, but it has product value because it makes the new scoped-memory/library model legible.

---

## 8. Thread-Scoped `queen_note`

### Current issue

`queen_note` storage is workspace-scoped.

### Wave 22 fix

Move storage to a thread-scoped path such as:

- `data/workspaces/{workspace_id}/threads/{thread_id}/queen_notes.yaml`

### Important implementation note

This is not just a helper-path change.

You may also need to:

- pass `thread_id` into the Queen note handler path
- update the tool dispatch call
- update any helper signatures that currently only accept `workspace_id`

---

## 9. Timestamp Formatting

Use the existing `timeAgo()` helper wherever raw ISO timestamps still appear in operator-facing views.

Primary targets:

- Queen chat
- colony chat
- event rows

This is a straightforward substitution, not a new formatting system.

---

## 10. Tree Toggle Usability

The current tree toggle logic is fine. The click target is the real problem.

The Wave 22 fix should:

- enlarge the hit area substantially
- add visible hover affordance

This should stay a focused usability change, not a navigation redesign.

---

## 11. Queen Pending State

Add a small pending/thinking state to Queen chat.

Important rule:

- set pending when the user sends a message
- clear pending on actual Queen response arrival
- do not clear it via timer

That makes the UI feel responsive without inventing fake progress.

---

## 12. Cost Display Truth

### Cloud spend

If cloud spend is not tracked and both values are zero, do not render a fake zero-value meter.

Prefer:

- `spend not tracked`

over:

- `$0.00 / $0.00`

### Near-zero cost

If a cost is nonzero but rounds to zero, render it as:

- `<$0.01`

This is a presentation truth fix, not a pricing-system change.

---

## 13. Round History Presentation

The current round-history surface should lead with what the colony produced.

Recommended order:

1. Final Output
2. Key artifacts / tool usage
3. Round-by-round detail

Use data already present in the frontend state or transcript-shaped data. Do not build a second backend just for this presentation change.

---

## 14. Browser Smoke Path

Keep this minimal.

Suggested coverage:

- app loads
- tree renders and toggles
- Queen chat accepts input
- timestamps are not raw ISO

This is enough to catch the trust/usability regressions Wave 22 is explicitly targeting.

---

## 15. Recommended File Changes

### Track A

- `src/formicos/surface/queen_runtime.py`
- `config/caste_recipes.yaml`
- `src/formicos/surface/agui_endpoint.py`

### Track B

- `src/formicos/engine/runner.py`
- `src/formicos/surface/routes/colony_io.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/components/knowledge-view.ts`
- `frontend/src/components/colony-detail.ts`
- `docs/decisions/037-scoped-colony-memory.md`

### Track C

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/tree-nav.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/atoms.ts`
- `frontend/src/components/round-history.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/colony-chat.ts` if needed
- `tests/browser/smoke.spec.ts`
- `package.json` if browser tooling needs to be declared

---

## 16. Final Guidance

Wave 22 should be disciplined about what kind of wave it is.

It is not:

- a protocol wave
- an event wave
- a new-architecture wave

It is:

- a judgment wave
- a scope-isolation wave
- a UI-trust wave

If the implementation stays inside those bounds, it will feel like product hardening instead of random polish.
