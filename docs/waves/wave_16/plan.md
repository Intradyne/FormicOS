# Wave 16 Plan: Dispatch Document

**Status:** Dispatch-ready
**Theme:** "Operator Control"
**Streams:** A (bug fixes + rename + operator audit) / B (Playbook + template authoring + UX polish) / C (colony file I/O + export + smoke polish)
**Contract stance:** Minimal opening - 1 new event (`ThreadRenamed`). Event union: 35 -> 36.
**Estimated effort:** 10-12 calendar days with 3 coders in parallel

---

## Wave boundary

Wave 16 is the operator-friction wave. Wave 15 proved the system launches and runs. Wave 16 fixes the places where a real operator tried to do something obvious and the product either failed, misled them, or made the action harder than it should be.

Wave 16 owns:
- bugs discovered during first real operator testing
- template authoring from the UI
- nav regrouping: Templates + Castes together, Models standalone
- colony file I/O: upload text context, export outputs as zip
- thread and colony rename
- readability, layout, and missing-action polish
- model registry classification and API key status correctness
- low-risk audit/polish inside touched operator-facing files

Wave 16 does not:
- add new colony mechanics
- change the round execution loop
- add new ports
- swap inference backends
- add multi-user/auth
- add pre-spawn document staging as a separate workflow

---

## Confirmed operator issues

These are confirmed against the completed Wave 15 repo state.

| # | Issue | Severity | Stream |
|---|---|---|---|
| 1 | Add thread button is wired to a no-op | High | A |
| 2 | Font size is too small across the shell and common panels | Medium | A |
| 3 | Five-tab nav can overflow / degrade on narrower widths | Medium | A |
| 4 | Gemini appears under local models and llama-cpp appears under cloud endpoints | High | A |
| 5 | Anthropic can show `connected` with an empty API key env var and the UI offers no useful guidance | High | A |
| 6 | No operator path to rename threads or colonies | Medium | A |
| 7 | No create/edit/duplicate template workflow in the UI | High | B |
| 8 | Templates and castes are grouped less naturally than templates and castes together | Medium | B |
| 9 | No upload/export path for colony documents and outputs | High | C |

Additional expectation for this wave:
- each stream performs a low-risk audit in its owned files and fixes adjacent operator-facing paper cuts if they are clearly in scope

---

## Success criteria

After Wave 16:

1. The operator can create threads from the UI.
2. The operator can rename threads and colonies from the UI.
3. The model registry correctly separates local and cloud providers.
4. Missing or empty API keys show `no_key` with guidance.
5. The app is readable at normal desktop viewing distance.
6. The 5-tab nav works at common desktop widths.
7. The operator can create a template from scratch.
8. The operator can edit and duplicate an existing template.
9. The operator can upload text documents to an existing colony.
10. The operator can export colony artifacts as a zip with item selection.
11. Any additional low-risk paper cuts found in owned files are either fixed or reported explicitly.

---

## Contract change: ThreadRenamed

Wave 16 opens the event union once for `ThreadRenamed`.

```python
class ThreadRenamed(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ThreadRenamed"] = "ThreadRenamed"
    workspace_id: str = Field(..., description="Parent workspace.")
    thread_id: str = Field(..., description="Stable thread identifier.")
    new_name: str = Field(..., description="New display name.")
    renamed_by: str = Field(default="operator", description="Actor.")
```

Important repo seam:
- `ThreadCreated.name` is currently both the initial display string and the stable thread identifier in projections
- Wave 16 does **not** rewrite thread addresses or replay keys
- `ThreadRenamed` is a display-name update only

Event union: 35 -> 36.

---

## Stream A: Bug Fixes + Rename + Operator Audit

**Owner:** 1 coder. Starts immediately.

### A.1 Add thread button

The broken seam is real:
- `@new-thread=${() => {}}` exists in `frontend/src/components/formicos-app.ts`

The fix is not frontend-only. Stream A must:
- wire the UI event in `formicos-app.ts`
- add `create_thread` to `frontend/src/types.ts` `WSCommandAction`
- add a `create_thread` command handler in `src/formicos/surface/commands.py`

`Runtime.create_thread()` already exists and should be reused.

Button treatment:
- make the `+` thread affordance clearly active
- use the existing accent/orange visual language

### A.2 Font/readability pass

The app is using many hardcoded `font-size` values across shared atoms and high-traffic components. This is not just one token change.

Required pass:
- audit `frontend/src/styles/shared.ts`
- audit `frontend/src/components/atoms.ts`
- audit the high-traffic shell and navigation components
- bump the size floor coherently, not component-by-component at random

Target outcome:
- body text feels like 13-14px, not 10-12px
- mono/data text is readable
- labels are still compact but not tiny

### A.3 Nav overflow

The current 5-tab nav lives in `formicos-app.ts`. Stream A should make the current nav stable before Stream B regroups it.

Acceptable fixes:
- `flex-wrap` when open
- tighter padding / min-width discipline
- better closed-sidebar icon-only behavior

### A.4 Model registry classification

The root cause is backend snapshot shaping, not just frontend rendering.

Current repo facts:
- `_build_local_models()` in `src/formicos/surface/view_state.py` excludes only `anthropic` and `openai`
- `_build_cloud_endpoints()` in `src/formicos/surface/view_state.py` includes every provider group

Required behavior:
- `llama-cpp/*` and other local providers belong in `localModels`
- `anthropic/*` and `gemini/*` belong in `cloudEndpoints`
- `frontend/src/components/model-registry.ts` remains a renderer, not the primary classifier

### A.5 API key status

Current repo facts:
- the snapshot builders check `os.environ.get(...) is not None`
- an empty string env var still looks "present"

Required fix:
- empty and missing env vars both produce `no_key`
- frontend shows useful guidance when `status === 'no_key'`
- no runtime key injection in Wave 16; point the operator to `.env`

Primary files:
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/model_registry_view.py` if helper parity is needed
- `frontend/src/components/model-registry.ts`

### A.6 Colony and thread rename

Colony rename:
- add operator rename affordance in `frontend/src/components/colony-detail.ts`
- add `rename_colony` WS command in `src/formicos/surface/commands.py`
- emit the existing `ColonyNamed` event with `named_by="operator"`

Thread rename:
- add `ThreadRenamed` in `src/formicos/core/events.py`
- update contracts and frontend mirrors
- add `rename_thread` WS command in `src/formicos/surface/commands.py`
- add `Runtime.rename_thread()` in `src/formicos/surface/runtime.py`
- update `src/formicos/surface/projections.py`
- add inline editable thread title in `frontend/src/components/thread-view.ts`

### A.7 Low-risk audit allowance

While touching thread/nav/model/naming surfaces, Stream A may also fix adjacent low-risk operator-facing issues inside its owned files, for example:
- copy clarity
- disabled/empty-state affordances
- small layout polish
- missing button states

Do not expand into Playbook/template authoring or file I/O.

### Stream A deliverables

- [ ] Add thread button works and is visually active/orange
- [ ] `create_thread` exists end-to-end on the WS path
- [ ] Readability pass lands across touched shell components
- [ ] Current nav no longer degrades at common desktop widths
- [ ] Model registry snapshot classifies local vs cloud correctly
- [ ] Empty/missing API keys show `no_key`
- [ ] Colony rename works from the UI
- [ ] Thread rename works from the UI
- [ ] Event union is 36 and mirrors are updated
- [ ] Low-risk audit fixes in owned files are included or explicitly reported

---

## Stream B: Playbook + Template Authoring + UX Polish

**Owner:** 1 coder. Starts immediately, but rereads `formicos-app.ts` after Stream A lands.

### B.1 Nav regrouping

The operator feedback is correct:
- Templates answer "what team do I deploy?"
- Castes answer "what kinds of agents exist?"
- Models answer "what compute is available?"

Wave 16 regroup:

| Tab | Contains | Rationale |
|---|---|---|
| Queen | Queen overview + chat | unchanged |
| Knowledge | skills + KG | unchanged |
| Playbook | templates + castes | team composition |
| Models | model registry | infrastructure |
| Settings | system settings | unchanged |

This replaces Fleet.

Implementation:
- replace `fleet-view.ts` with `playbook-view.ts`
- Playbook sub-tabs: Templates / Castes
- Models tab renders `model-registry` directly
- update imports and NAV in `formicos-app.ts`

### B.2 Template create/edit/duplicate

Current repo facts:
- backend already supports `POST /api/v1/templates`
- the route already accepts `template_id`, `version`, `tags`, `budget_limit`, and `max_rounds`
- templates are versioned in `src/formicos/surface/template_manager.py`
- the current browser UI is read-only and drops some of that shape in `frontend/src/components/template-browser.ts`

Wave 16 template editor should:
- create from scratch
- edit an existing template
- duplicate a template

Important schema rule:
- keep the current flat template schema
- use top-level `castes`, `budget_limit`, and `max_rounds`
- do **not** invent a nested governance object in this wave

### B.3 Frontend type/data-shape work

The editor flow likely needs a second pass on frontend template shape:
- `frontend/src/components/template-browser.ts`
- `frontend/src/types.ts`

Carry through:
- `template_id`
- `version`
- `tags`
- `budget_limit`
- `max_rounds`

Edit behavior:
- save a new version with the same `template_id`
- increment version client-side or in the save flow consistently

### B.4 Low-risk audit allowance

While touching Playbook/template surfaces, Stream B may also fix adjacent low-risk UX issues in owned files, for example:
- empty states
- missing secondary actions
- modal copy
- tab spacing/polish

Do not reopen Stream A bugs or Stream C file I/O.

### Stream B deliverables

- [ ] Playbook replaces Fleet
- [ ] Models tab is standalone
- [ ] New Template action exists in the UI
- [ ] Edit action exists in the UI
- [ ] Duplicate action exists in the UI
- [ ] Template editor uses the live flat schema
- [ ] Template edit flow preserves `template_id` and versioning semantics
- [ ] Low-risk audit fixes in owned files are included or explicitly reported

---

## Stream C: Colony File I/O + Export + Smoke Polish

**Owner:** 1 coder. Starts immediately for backend work; rereads `colony-detail.ts` after Stream A lands.

### C.1 Decision

File I/O is a surface-layer concern:
- REST endpoints
- filesystem storage
- no new events

### C.2 Upload scope

Wave 16 upload is colony-scoped:
- `POST /api/v1/colonies/{id}/files`
- store files under the data directory
- inject uploaded text into a running colony via `colony_manager.inject_message()`

Wave 16 does **not** add a separate pre-spawn upload workflow.

Alpha limits:
- text files only (`.txt`, `.md`, `.py`, `.json`, `.yaml`, `.csv`)
- 10MB per file
- 50MB per colony
- injected text truncated for context safety

### C.3 Export scope

Wave 16 export is zip-based with item selection:
- uploaded source documents from filesystem
- round outputs from `colony.round_records[*].agent_outputs`
- colony chat transcript from `colony.chat_messages`
- extracted skills if they can be gathered by colony/source-colony
- code/tool summaries only if they are actually available from retained state or safe event-store scan

Do not implement export against non-existent fields like `agent.output`, `msg.ts`, or `msg.text`.

### C.4 Selection model

Required operator behavior:
- choose export categories
- choose specific uploaded files when downloads include source documents

Acceptable route shape:
- `GET /api/v1/colonies/{id}/export?items=uploads,outputs,chat,skills&uploads=file1.md,file2.txt`

### C.5 Frontend surface

Add to colony detail:
- Upload Files action
- file picker and upload status
- export panel with item selection
- uploaded-file list / selection affordance

### C.6 Low-risk audit allowance

While touching upload/export UX, Stream C may also fix adjacent low-risk issues in its owned files, for example:
- empty/error states
- file size/help copy
- download button clarity

### Stream C deliverables

- [ ] Upload endpoint exists
- [ ] Export endpoint exists
- [ ] Files are stored in the data directory
- [ ] Running-colony upload injection works
- [ ] Export uses real projection/file data sources
- [ ] Upload UI exists
- [ ] Export UI exists with item selection
- [ ] Specific uploaded files can be selected for inclusion
- [ ] Low-risk audit fixes in owned files are included or explicitly reported

---

## Shared-workspace merge discipline

Streams are mostly parallel, with two real coordination points.

| File | Streams | Resolution |
|---|---|---|
| `frontend/src/components/formicos-app.ts` | A + B | A lands bug fixes first. B rereads and does the nav regroup second. |
| `frontend/src/components/colony-detail.ts` | A + C | A lands rename affordances first. C rereads and adds upload/export second. |
| `frontend/src/types.ts` | A + B | A owns command/event changes first. B may take a second pass for template editor shape. |

Primary ownership map:

| File | Stream | Notes |
|---|---|---|
| `src/formicos/core/events.py` | A | add `ThreadRenamed` |
| `docs/contracts/events.py` | A | mirror `ThreadRenamed` |
| `src/formicos/surface/runtime.py` | A | add `rename_thread()` |
| `src/formicos/surface/commands.py` | A | add `create_thread`, `rename_colony`, `rename_thread` |
| `src/formicos/surface/projections.py` | A | add `ThreadRenamed` handler |
| `src/formicos/surface/view_state.py` | A | fix local/cloud model grouping and `no_key` derivation |
| `src/formicos/surface/model_registry_view.py` | A | keep helper parity if needed |
| `frontend/src/components/formicos-app.ts` | A then B | thread button, nav fix, then Playbook regroup |
| `frontend/src/components/model-registry.ts` | A | `no_key` UX and registry polish |
| `frontend/src/components/thread-view.ts` | A | thread rename |
| `frontend/src/components/colony-detail.ts` | A then C | rename first, file I/O second |
| `frontend/src/styles/shared.ts` | A | readability pass |
| `frontend/src/components/atoms.ts` | A | readability pass |
| `frontend/src/components/playbook-view.ts` | B | replaces Fleet |
| `frontend/src/components/template-browser.ts` | B | create/edit/duplicate entry points |
| `frontend/src/components/template-editor.ts` | B | new |
| `src/formicos/surface/app.py` | C | upload/export endpoints |

Frozen files:
- `src/formicos/core/types.py`
- `src/formicos/core/ports.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- `src/formicos/adapters/vector_qdrant.py`
- `src/formicos/adapters/knowledge_graph.py`

---

## Not in Wave 16

| Feature | Why deferred |
|---|---|
| Runtime API key hot-reload | not required for the operator-control pass |
| Binary file handling (PDF/images) | text-only alpha is enough for this wave |
| Pre-spawn document staging | separate workflow, not necessary for this pass |
| Queen-composed dashboards | later wave |
| Multi-user/auth | single-operator product |
| New colony mechanics | not an operator-control problem |

---

## Exit gate

- [ ] Thread creation works from the UI
- [ ] Thread and colony rename work from the UI
- [ ] Fonts/readability are materially improved
- [ ] Current nav no longer degrades at common widths
- [ ] Model registry snapshot separates local vs cloud correctly
- [ ] `no_key` appears correctly for empty or missing provider secrets
- [ ] Playbook replaces Fleet
- [ ] Template create/edit/duplicate all work
- [ ] Template editor uses the live flat template schema
- [ ] Upload works for text files on existing colonies
- [ ] Export works as zip with selection
- [ ] Any extra low-risk paper cuts found during stream audits are fixed or explicitly reported
- [ ] Frontend build passes
- [ ] Existing tests still pass
