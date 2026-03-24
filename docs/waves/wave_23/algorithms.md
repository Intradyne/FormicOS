# Wave 23 Algorithms - Implementation Reference

**Wave:** 23 - "Operator Smoothness + External Handshake"  
**Purpose:** Repo-accurate implementation guidance for the three tracks.

---

## Section 1. Empty states and colony-detail outcome-first layout

### Empty state pattern

Reuse the existing Lit conditional pattern and the existing `.empty-hint` style where possible:

```ts
${items.length === 0
  ? html`<div class="empty-hint">Guidance text here</div>`
  : html`...normal content...`}
```

Target surfaces:
- `queen-chat.ts`
- `knowledge-view.ts`
- `thread-view.ts`
- `round-history.ts`
- `colony-detail.ts`

### Colony detail progress

The snapshot already carries:
- `c.round`
- `c.maxRounds`
- `c.rounds`

So the running-state surface can stay frontend-only:

```ts
${c.status === 'running' ? html`
  <div class="progress-block">
    <div class="progress-label">Round ${c.round} / ${c.maxRounds}</div>
    <div class="progress-bar">
      <div class="progress-fill" style=${`width:${(c.round / c.maxRounds) * 100}%`}></div>
    </div>
  </div>
` : nothing}
```

### Colony detail final output

Do not invent a new backend field. Build from the latest round already present in `c.rounds`:

```ts
const rounds = c.rounds ?? [];
const last = rounds.length > 0 ? rounds[rounds.length - 1] : null;
const agentsWithOutput = (last?.agents ?? []).filter(a => !!a.output);
```

Render that before the rest of the detail metadata.

---

## Section 2. First-run welcome refinement

The first-run Queen welcome already exists in the app lifespan/bootstrap path. This is a text change, not a new bootstrap feature.

Suggested shape:

```text
Welcome to FormicOS. I am the Queen, your strategic coordinator.

Try asking me to write a haiku, review a code snippet, or research a topic.

Tip: upload documents in Knowledge -> Library to make them searchable.
```

Keep it short and concrete.

---

## Section 3. Prior work surfacing on spawn

### Honest implementation point

If this logic lives in `_tool_spawn_colony()`, it is post-decision. That means:
- the Queen has already decided to spawn
- the Queen has already chosen team/rounds/budget
- the added context can help the operator and follow-up conversation
- it does not influence the earlier LLM decision

That scope is still useful and honest.

### Suggested implementation

After the colony is spawned and the main success text is built:

```python
vector_port = self._runtime.vector_store
if vector_port is not None:
    skill_coll = getattr(vector_port, "_default_collection", None) or "skill_bank_v2"
    hits = []
    for collection in (workspace_id, skill_coll):
        try:
            hits.extend(await vector_port.search(
                collection=collection,
                query=task,
                top_k=3,
            ))
        except Exception:
            pass

    unique = []
    seen = set()
    for hit in hits:
        if hit.id in seen:
            continue
        seen.add(hit.id)
        unique.append(hit)

    top = unique[:3]
    if top:
        lines = []
        for hit in top:
            source = hit.metadata.get("source_colony") or hit.metadata.get("source_file") or "unknown"
            preview = hit.content[:160].replace("\n", " ")
            lines.append(f"- [{hit.score}] {preview} (source: {source})")
        spawn_msg += "\n\nRelated prior work:\n" + "\n".join(lines)
```

Important constraints:
- no fake relevance threshold
- top hits only
- show provenance
- spawn must still succeed even if search fails or memory is empty

---

## Section 4. Quality-aware Queen follow-up

Current `follow_up_colony()` behavior is flat. Make it branch on quality:

```python
if quality >= 0.7:
    summary = (
        f"Colony **{name}** completed well after {rounds} round(s). "
        f"Quality: {quality:.0%}. Cost: ${cost:.4f}."
    )
elif quality >= 0.4:
    summary = (
        f"Colony **{name}** completed after {rounds} round(s) "
        f"with moderate quality ({quality:.0%}). "
        "Results may benefit from review."
    )
else:
    summary = (
        f"Colony **{name}** completed with low quality ({quality:.0%}). "
        "Consider retrying with a different approach or team."
    )

if skills:
    summary += f" {skills} skill(s) extracted."
```

This is deterministic and grounded in state the engine already computes.

---

## Section 5. Save-as-preference path

### Frontend

Add a small save affordance to Queen messages only. On click:
- dispatch `save-queen-note`
- include thread id and content
- trim content to the same cap the backend already expects

```ts
private _saveAsPreference(content: string) {
  this.dispatchEvent(new CustomEvent('save-queen-note', {
    detail: { content: content.slice(0, 500) },
    bubbles: true,
    composed: true,
  }));
}
```

`formicos-app.ts` should catch that event and send a WS command through the existing command path.

### Backend

Use `commands.py`, because that is already the WS command dispatch surface.

Do not create a parallel note persistence path. The cleanest implementation is:
- extract a tiny shared helper in `QueenAgent` for saving one thread note, or
- reuse the existing `queen_note` tool-save path internally

Then the command handler can call that shared path.

Example target shape:

```python
async def _handle_save_queen_note(
    workspace_id: str,
    payload: dict[str, Any],
    runtime: Runtime,
) -> dict[str, Any]:
    queen = runtime.queen
    if queen is None:
        return {"error": "queen unavailable"}

    thread_id = payload["threadId"]
    content = payload["content"]
    queen.save_thread_note(workspace_id, thread_id, content)
    return {"status": "saved"}
```

If `save_thread_note()` does not exist yet, create it as a small shared helper that both the WS command path and `_tool_queen_note(... action='save' ...)` can reuse.

---

## Section 6. A2A task lifecycle

### Route module

Create a new route module:

`src/formicos/surface/routes/a2a.py`

It should export a normal `routes(**deps)` factory like the rest of the surface route modules.

### Endpoint set

Required endpoints:
- `POST /a2a/tasks`
- `GET /a2a/tasks`
- `GET /a2a/tasks/{task_id}`
- `GET /a2a/tasks/{task_id}/result`
- `DELETE /a2a/tasks/{task_id}`

### Task identity

Tasks are colonies:
- `task_id == colony_id`
- no second store
- no second event stream

### Submit flow

`POST /a2a/tasks` should:

1. parse `description`
2. load templates asynchronously with `await load_templates()`
3. select a team deterministically
4. choose thread name, e.g. `a2a-{description_slug}`
5. call `runtime.spawn_colony(...)`
6. start the colony with `colony_manager.start_colony(...)`
7. return a task envelope

### Deterministic team selection

Keep this helper deterministic and synchronous once templates are loaded:

```python
def _select_team(description: str, templates: list[Any]) -> tuple[list[CasteSlot], str, int, float]:
    words = set(description.lower().split())

    for tmpl in templates:
        tags = {t.lower() for t in getattr(tmpl, "tags", [])}
        if tags & words:
            return (list(tmpl.castes), tmpl.strategy, tmpl.max_rounds, tmpl.budget_limit)

    if words & {"review", "audit", "check", "inspect"}:
        return ([CasteSlot(caste="reviewer")], "sequential", 5, 1.0)
    if words & {"research", "summarize", "analyze", "explain", "compare"}:
        return ([CasteSlot(caste="researcher")], "sequential", 8, 1.0)
    if words & {"code", "implement", "write", "build", "fix", "debug", "script"}:
        return ([CasteSlot(caste="coder"), CasteSlot(caste="reviewer")], "stigmergic", 10, 2.0)

    return ([CasteSlot(caste="coder"), CasteSlot(caste="reviewer")], "stigmergic", 10, 2.0)
```

Do not call the Queen LLM here.

### Status/result/cancel

`GET /a2a/tasks/{id}` should read the colony projection directly.

`GET /a2a/tasks/{id}/result` should call:

```python
from formicos.surface.transcript import build_transcript
```

and wrap the transcript in a task-oriented envelope.

`DELETE /a2a/tasks/{id}` should call `runtime.kill_colony(...)` and preserve honest status handling:
- 404 not found
- 409 if already terminal

### No streaming in Wave 23

Do not add a `stream_url` field.

Do not imply that `POST /ag-ui/runs` can attach to an already-running A2A task. It cannot.

If a future wave adds:
- `GET /a2a/tasks/{id}/events`

that can build on the existing colony subscription infrastructure. It is not part of this wave.

---

## Section 7. Agent Card and registry update

When A2A lands, update the Agent Card and capability registry to advertise:
- A2A task support
- `/a2a/tasks` endpoint

Streaming can still remain `true` at the Agent Card level because AG-UI exists, but the A2A docs must clearly state that A2A itself is poll/result only in Wave 23.

---

## Section 8. File map

### Track A
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/knowledge-view.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/round-history.ts`
- `frontend/src/components/colony-detail.ts`
- `src/formicos/surface/app.py`
- `frontend/package.json`
- `CONTRIBUTING.md`

### Track B
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/commands.py`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/formicos-app.ts`
- `config/caste_recipes.yaml`

### Track C
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/__init__.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/app.py`
- `docs/A2A-TASKS.md`
