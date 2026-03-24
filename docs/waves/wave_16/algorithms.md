# Wave 16 Algorithms and Implementation Reference

**Audience:** Offline coders implementing Wave 16.
**Repo reality:** Wave 15 is complete. The current shell is live, but several operator-control seams are either missing or pointed at the wrong layer.

---

## 1. Stream A: bug fixes, rename, and operator audit

### 1.1 Thread creation is a full WS surface fix

The broken UI seam is real:
- `@new-thread=${() => {}}` exists in `frontend/src/components/formicos-app.ts`

But the repo already has:
- `Runtime.create_thread()` in `src/formicos/surface/runtime.py`

What is missing:
- `create_thread` in `frontend/src/types.ts` `WSCommandAction`
- `create_thread` handler in `src/formicos/surface/commands.py`
- frontend wiring in `formicos-app.ts`

Use the existing command-handler pattern:

```python
async def _handle_create_thread(
    workspace_id: str,
    payload: dict[str, Any],
    runtime: Runtime,
) -> dict[str, Any]:
    thread_id = await runtime.create_thread(workspace_id, payload["name"])
    return {"threadId": thread_id}
```

And register it in `_COMMAND_HANDLERS`.

Frontend wiring:

```ts
@new-thread=${() => {
  const name = `thread-${Date.now().toString(36)}`;
  store.send('create_thread', this.activeWorkspaceId, { name });
}}
```

### 1.2 Colony rename uses the existing event

Do not open a new colony-name contract.

Use:
- `ColonyNamed` in `src/formicos/core/events.py`
- a new `rename_colony` WS command
- the existing projection path already used by Queen naming

Pattern:

```python
async def _handle_rename_colony(
    workspace_id: str,
    payload: dict[str, Any],
    runtime: Runtime,
) -> dict[str, Any]:
    colony_id = payload["colonyId"]
    new_name = payload["name"]
    colony = runtime.projections.get_colony(colony_id)
    if colony is None:
        return {"error": f"colony '{colony_id}' not found"}

    address = f"{colony.workspace_id}/{colony.thread_id}/{colony.id}"
    await runtime.emit_and_broadcast(ColonyNamed(
        seq=0,
        timestamp=_now(),
        address=address,
        colony_id=colony_id,
        display_name=new_name,
        named_by="operator",
    ))
    return {"status": "renamed"}
```

### 1.3 Thread rename is display-only

Important repo fact:
- `ThreadCreated.name` is currently both the initial display string and the stable thread identifier in projections

Wave 16 must not rewrite thread addresses or replay keys.

Use `ThreadRenamed` only to update presentation:

```python
class ThreadRenamed(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ThreadRenamed"] = "ThreadRenamed"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    new_name: str = Field(...)
    renamed_by: str = Field(default="operator")
```

Projection update should:
- locate the thread by `thread.id == event.thread_id`
- update `thread.name`
- leave the dictionary key and addresses alone

### 1.4 Model registry classification belongs in the snapshot builder

The operator-visible bug is not primarily in `model-registry.ts`.

Current repo facts:
- `_build_local_models()` in `src/formicos/surface/view_state.py` excludes only `anthropic` and `openai`
- `_build_cloud_endpoints()` includes every provider

Fix `view_state.py` first.

A safe rule:

```python
LOCAL_PROVIDERS = {"llama-cpp", "ollama", "local"}
CLOUD_PROVIDERS = {"anthropic", "gemini"}
```

Then:
- emit only local providers under `localModels`
- emit only cloud providers under `cloudEndpoints`

Frontend `model-registry.ts` should keep rendering whatever the snapshot gives it.

### 1.5 `no_key` must treat empty env vars as missing

Current bug:

```python
api_key_set = os.environ.get(model.api_key_env) is not None
```

That treats `""` as present.

Use truthiness instead:

```python
api_key_set = bool(os.environ.get(model.api_key_env or ""))
status = "connected" if api_key_set else "no_key"
```

Apply in:
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/model_registry_view.py` if the helper remains in use

### 1.6 Readability pass is a hardcoded-size audit

`frontend/src/styles/shared.ts` does not currently define font-size tokens, so this is not a one-line token swap.

Start with:
- `frontend/src/styles/shared.ts`
- `frontend/src/components/atoms.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/template-browser.ts`

Audit strategy:
- anything in the 7.5-10px range is suspect
- body text should land closer to 13-14px
- mono/data text should land closer to 11-12px
- labels can stay smaller, but not tiny

### 1.7 Stream A audit allowance

If Stream A finds adjacent low-risk issues in the same owned files, it should fix them while already in those files. Good candidates:
- copy clarity
- hover/focus states
- disabled button states
- missing empty-state hints

Do not sprawl into Playbook/template authoring or file I/O.

---

## 2. Stream B: Playbook and template authoring

### 2.1 Replace Fleet with Playbook

The current shell imports `fleet-view.ts` and exposes a `fleet` tab in `formicos-app.ts`.

Wave 16 regroup:
- `Playbook` tab hosts Templates + Castes
- `Models` becomes its own top-level tab

Implementation options:
- rename `fleet-view.ts` to `playbook-view.ts`
- or add `playbook-view.ts` and delete the Fleet wiring once the new tab is in place

Either is fine. The important part is the final shell shape, not preserving the old file name.

### 2.2 Template editor must preserve the live backend shape

Current backend route:
- `POST /api/v1/templates` in `src/formicos/surface/app.py`

It already accepts:
- `template_id`
- `version`
- `castes`
- `strategy`
- `budget_limit`
- `max_rounds`
- `tags`
- `source_colony_id`

Current frontend browser drops part of that shape.

Wave 16 editor should carry:
- `template_id`
- `version`
- `tags`
- `budget_limit`
- `max_rounds`

Important schema rule:
- use the live flat schema
- do not introduce a nested `governance` block in this wave

### 2.3 Editor component shape

Suggested state:

```ts
@customElement('fc-template-editor')
export class FcTemplateEditor extends LitElement {
  @property({ type: Object }) template: TemplateInfo | null = null;
  @property({ type: Array }) castes: CasteDefinition[] = [];

  @state() private templateId = '';
  @state() private version = 1;
  @state() private name = '';
  @state() private description = '';
  @state() private tags: string[] = [];
  @state() private slots: CasteSlot[] = [];
  @state() private strategy: CoordinationStrategy = 'stigmergic';
  @state() private maxRounds = 12;
  @state() private budgetUsd = 5.0;
}
```

Create mode:
- omit `template_id` or generate via backend default
- save with `version = 1`

Edit mode:
- preserve `template_id`
- save `version = template.version + 1`

Duplicate mode:
- clear `template_id`
- reset `version = 1`
- prefill the rest

### 2.4 Template browser changes

Add explicit actions:
- New Template
- Edit
- Duplicate

The current browser already knows how to fetch and normalize templates from `/api/v1/templates`. Extend that normalization instead of replacing it.

### 2.5 Stream B audit allowance

While touching Playbook/template surfaces, fix adjacent low-risk issues in owned files, such as:
- empty-state copy
- missing button hierarchy
- modal spacing
- tab-label clarity

---

## 3. Stream C: colony file I/O and export

### 3.1 Upload is colony-scoped, not pre-spawn

Wave 16 route:

```python
Route("/api/v1/colonies/{colony_id:str}/files", upload_colony_files, methods=["POST"])
```

The colony must already exist.

Upload flow:
- store files under the data dir
- if the colony is running, inject a truncated text block via `colony_manager.inject_message()`
- if the colony is not running, keep the files available for export and for later extension, but do not invent a separate pre-spawn queue in Wave 16

### 3.2 Upload endpoint pattern

```python
async def upload_colony_files(request: Request) -> JSONResponse:
    colony_id = request.path_params["colony_id"]
    colony = runtime.projections.get_colony(colony_id)
    if colony is None:
        return JSONResponse({"error": "colony not found"}, status_code=404)

    form = await request.form()
    upload_dir = data_dir / "workspaces" / colony.workspace_id / "colonies" / colony_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, Any]] = []
    total_bytes = 0

    for value in form.values():
        if not hasattr(value, "read"):
            continue
        content = await value.read()
        total_bytes += len(content)
        if len(content) > 10 * 1024 * 1024:
            continue
        if total_bytes > 50 * 1024 * 1024:
            break

        filename = Path(value.filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv"}:
            continue

        path = upload_dir / filename
        path.write_bytes(content)
        uploaded.append({"name": filename, "bytes": len(content)})

        if colony.status == "running" and runtime.colony_manager is not None:
            text = content.decode("utf-8", errors="replace")
            await runtime.colony_manager.inject_message(
                colony_id,
                f"[Uploaded Document: {filename}]\\n{text[:8000]}",
            )

    return JSONResponse({"uploaded": uploaded})
```

### 3.3 Export must use real projection fields

Do not export from fake fields like:
- `agent.output`
- `msg.ts`
- `msg.text`

Use:
- `colony.round_records[*].agent_outputs`
- `colony.chat_messages[*].content`
- `colony.chat_messages[*].timestamp`
- uploaded files on disk

Suggested export shape:

```python
async def export_colony(request: Request) -> Response:
    colony_id = request.path_params["colony_id"]
    colony = runtime.projections.get_colony(colony_id)
    if colony is None:
        return JSONResponse({"error": "colony not found"}, status_code=404)

    items = set(request.query_params.get("items", "uploads,outputs,chat").split(","))
    selected_uploads = {
        name for name in request.query_params.get("uploads", "").split(",") if name
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if "uploads" in items:
            upload_dir = data_dir / "workspaces" / colony.workspace_id / "colonies" / colony_id / "uploads"
            if upload_dir.exists():
                for path in sorted(upload_dir.iterdir()):
                    if selected_uploads and path.name not in selected_uploads:
                        continue
                    if path.is_file():
                        zf.writestr(f"uploads/{path.name}", path.read_bytes())

        if "outputs" in items:
            for round_rec in colony.round_records:
                for agent_id, output in round_rec.agent_outputs.items():
                    zf.writestr(
                        f"outputs/round-{round_rec.round_number}/{agent_id}.txt",
                        output,
                    )

        if "chat" in items:
            lines = [
                f"[{msg.timestamp}] {msg.sender}: {msg.content}"
                for msg in colony.chat_messages
            ]
            zf.writestr("chat.md", "\\n\\n".join(lines))

        if "skills" in items:
            # Implementation may query skill storage by source colony if feasible.
            ...
```

If structured code-execution artifacts are not retained cleanly enough, do not fake a separate `code/` export tree in Wave 16. Fold code/tool summaries into chat or defer them explicitly.

### 3.4 Frontend export panel

Required UX:
- category checkboxes
- specific uploaded-file selection
- clear disabled states when no uploads or no exported data exists

Suggested controls:
- Uploaded files
- Agent outputs
- Chat transcript
- Extracted skills

### 3.5 Stream C audit allowance

While touching upload/export surfaces, fix adjacent low-risk issues in owned files, such as:
- empty/error-state copy
- file-limit messaging
- upload success/failure clarity
- export selection usability

---

## 4. Validation guidance

Stream A:
- `python scripts/lint_imports.py`
- targeted pytest for events/projections/WS command handling
- `cd frontend && npm run build`

Stream B:
- `cd frontend && npm run build`
- targeted template/browser/component tests if added

Stream C:
- targeted API tests for upload/export
- `python -m pytest -q`
- `cd frontend && npm run build`
- smoke the real upload/export flow if possible

---

## 5. Dispatch cautions

- `formicos-app.ts` is a serialized overlap: Stream A first, Stream B second
- `colony-detail.ts` is a serialized overlap: Stream A first, Stream C second
- `frontend/src/types.ts` may need a second pass by Stream B after Stream A changes command/event shape
- do not implement against stale pseudo-fields; use the current repo data structures
