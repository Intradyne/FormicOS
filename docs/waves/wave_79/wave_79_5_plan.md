**Theme:** Make files first-class workflow objects for operators and for
the Queen, using the live FormicOS substrate instead of introducing a host
mount or a stage-engine.

**Relationship to Wave 79:** Wave 79 improves local-model quality and
prompt efficiency. Wave 79.5 turns the existing file substrate
(`target_files`, `input_sources`, working memory, artifacts, workspace
library ingestion) into a visible operator workflow.

**Estimated total change:** ~350-550 lines across frontend-heavy surfaces
plus a small additive metadata change in the Queen follow-up path.

---

## Problem statement

The codebase already has the main file-workflow primitives:

- `target_files` on `ColonySpawned`
- `input_sources` for colony chaining
- Queen working-memory tools (`write_working_note`, `promote_to_artifact`)
- workspace document ingestion
- workspace / working-memory / artifact file surfaces

But the operator still cannot use them naturally:

1. `target_files` exists in the substrate but is not easy to select.
2. result cards show file counts, not concrete outputs.
3. uploaded documents are ingested through the Knowledge tab, but the
   Workspace tab gives no obvious path.
4. colony-to-colony file handoff is possible, but mostly invisible.

This creates a gap between "FormicOS can coordinate through files" and
"the operator can actually drive and audit file-mediated workflows."

---

## Track A: Target-File Workflow in the Main UI

### Goal

Make `target_files` an obvious part of colony creation and workspace
exploration.

### What to build

#### A1: File picker in `colony-creator.ts`

Add a compact file picker that can select from:

- workspace files
- AI filesystem artifacts

Use existing APIs:

- `GET /api/v1/workspaces/{workspace_id}/files`
- `GET /api/v1/workspaces/{workspace_id}/ai-filesystem`
- `POST /api/v1/preview-colony` already accepts `target_files`

The picker should:

- allow multi-select
- show selected count
- show short relative paths, not full JSON blobs
- write the selection into the colony preview request as `target_files`

#### A2: One shared draft target-file state in `formicos-app.ts`

Do not let `workspace-browser.ts` and `colony-creator.ts` invent separate
temporary file selections.

Use one ephemeral UI state in the app shell:

- Workspace tab actions can seed it
- colony creator can edit it
- preview confirmation clears it after dispatch/cancel

#### A3: Workspace actions for file rows

On workspace file rows, add:

- `Ask Queen About This`
- `Use As Target File`
- `Open In Colony Creator`

Dispatch order:

- first-class support for `Use As Target File` and `Open In Colony Creator`
  should land together with the shared draft state
- `Ask Queen About This` should prefill the Queen chat input with the file
  path and a short prompt seed, but should not auto-send

### Files

| File | Change |
|------|--------|
| `frontend/src/components/colony-creator.ts` | file picker + selected target files UI |
| `frontend/src/components/workspace-browser.ts` | file-row actions |
| `frontend/src/components/formicos-app.ts` | shared draft target-file state + wiring |
| `frontend/src/components/queen-chat.ts` | Add `@property() draftMessage` for external prefill (currently `@state() private input` at line 199 — not settable from parent) |

### Validation

```bash
npm run build

# Manual:
# 1. pick a file in Workspace
# 2. seed colony creator
# 3. preview shows target files
# 4. confirmed colony carries target_files through
```

---

## Track B: Output Trace and File Handoff Visibility

### Goal

Make colony outputs inspectable as concrete files rather than abstract
success counts.

### What to build

#### B1: Add output filenames to result-card metadata

`queen_runtime.py` already computes `filesChanged` from colony artifacts
at lines 574-582. It filters `colony.artifacts` by `artifact_type` in
`("file", "code", "patch")` and stores `len(_file_arts)` as
`result_meta["filesChanged"]`.

Extend this to also include a `"outputFiles"` list with up to 5 filenames
extracted from the same `_file_arts` list. No new fetch needed — the data
is already available when the result card is built.

Note: `ResultCardMeta` in `fc-result-card.ts` does not currently declare
`filesChanged` — it's accessed via unsafe cast. Track B should add both
`filesChanged?: number` and `outputFiles?: string[]` to the interface.

#### B2: Show concrete output names in `fc-result-card.ts`

Keep the compact count badge, but also show:

- first few output filenames
- clear click target to colony detail or workspace view

This closes the loop:

- task
- colony
- output files
- follow-on work

#### B3: "Use Output As Next Input" on stable outputs

For artifact / output surfaces where the source colony is known, add a
bounded follow-on action that seeds the next colony with:

- `input_from` / `input_sources` from the source colony
- `target_files` from the output files the operator selected

This is the lightest version of file-backed inter-agent communication that
fits the current system without new event contracts.

Implementation note:

- prefer existing `input_sources` + `target_files`
- do not invent `InputSource(type="file")` yet
- do not summarize the prior colony's output into long prose if a real file
  handoff is available

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/queen_runtime.py` | additive result-card metadata for output file names |
| `frontend/src/components/fc-result-card.ts` | show concrete outputs |
| `frontend/src/components/colony-detail.ts` | bounded "use output as next input" action if source colony is known |
| `frontend/src/components/formicos-app.ts` | handoff wiring into creator/chat flow |
| `frontend/src/types.ts` | additive result-card metadata typing for output file names |

### Validation

```bash
npm run build

# Manual:
# 1. complete a colony that writes file/code/patch artifacts
# 2. result card shows count + names
# 3. selecting a follow-on action seeds the next colony with real file context
```

---

## Track C: Document Ingestion and Working-Memory Truth

### Goal

Make the existing ingestion and working-memory flows discoverable from the
Workspace tab.

### What to build

#### C1: `Upload & Ingest` in `workspace-browser.ts`

Expose the same workspace-ingestion flow already present in
`knowledge-view.ts`:

- same endpoint
- same allowed file types
- same "ingested X chunks" style status

This is not a new ingestion subsystem. It is a second entry point to an
existing one.

#### C2: Working memory / artifact actions

On AI filesystem rows:

- allow `Open`
- allow `Promote to Artifact` when the item lives under `runtime/`

Make this concrete with two thin endpoints rather than hand-waving:

- `GET /api/v1/workspaces/{workspace_id}/ai-filesystem/file`
  - query: `scope=runtime|artifacts`, `path=...`
  - returns preview text for supported file types
- `POST /api/v1/workspaces/{workspace_id}/ai-filesystem/promote`
  - body: `{ "path": "...", "target_subdir": "deliverables" }`
  - wraps an updated artifact-promotion seam that accepts a runtime-relative
    path, not basename search

Use the existing Queen tool conceptually, but the UI should not force the
operator to type a Queen tool call by hand.

Important correctness note:

- `promote_to_artifact()` at ai_filesystem.py:86 does
  `safe_name = Path(runtime_filename).name` then `runtime.rglob(safe_name)`
  — basename search, takes first match
- that is not deterministic enough for UI row actions (multiple files with
  same basename in different subdirectories)
- Track C should make promotion path-based and traversal-safe

#### C3: Truthful section language

Keep the three file surfaces distinct and honest:

- `Operator Files`
- `Working Memory`
- `Workspace Files`

Do not relabel workspace files as host project files. They are the FormicOS
workspace library and shared file surface.

### Files

| File | Change |
|------|--------|
| `frontend/src/components/workspace-browser.ts` | `Upload & Ingest` + working-memory actions |
| `src/formicos/surface/ai_filesystem.py` | path-safe preview/promote helpers |
| `src/formicos/surface/routes/api.py` | thin AI filesystem preview + promote endpoints |

### Validation

```bash
npm run build

# Manual:
# 1. Upload & Ingest is visible in Workspace
# 2. ingested docs appear in workspace library and become searchable
# 3. working-memory items can be opened
# 4. runtime items can be promoted to artifacts
```

---

## Merge order

```text
Track A (target-file workflow)          - first
Track B (output trace + handoff)        - second
Track C (ingest + working-memory truth) - third
```

Reasoning:

- Track A defines the shared draft-file state used by later actions.
- Track B builds the follow-on handoff loop on top of that.
- Track C is mostly discoverability / truth polish and can integrate last.

---

## What 79.5 does NOT do

- no host project mount
- no hard runtime charter
- no NLAH / stage-engine
- no new `InputSource(type="file")`
- no multi-project workspace binding
- no fake renaming of workspace files to "Project Files"

---

## Success conditions

1. Operators can select target files without typing paths manually.
2. Colony previews visibly include selected target files.
3. Colony result cards show concrete output names, not only counts.
4. A follow-on colony can be seeded from prior colony outputs using the
   existing `input_sources` + `target_files` seams.
5. `Upload & Ingest` is visible from the Workspace tab.
6. The three file surfaces remain distinct and truthful.
