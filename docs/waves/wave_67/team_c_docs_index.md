# Wave 67.5 - Team C: Documentation Indexer Addon

**Wave:** 67.5 (surfaces)
**Track:** 6 - Documentation Indexer Addon
**Prerequisite:** Wave 66 addon infrastructure is landed; Wave 67.0 is landed

---

## Mission

Operators already have semantic code search, but there is still no parallel
semantic path for project documentation. This track adds a new addon that:

- indexes `.md`, `.rst`, `.txt`, and `.html`
- exposes `semantic_search_docs` and `reindex_docs`
- publishes a knowledge-tab status panel
- stores results in a separate `docs_index` collection

Your job: build the addon as a new vertical slice by following the existing
`codebase-index` addon pattern as closely as possible.

Structural invariant:

- documentation chunks belong in the addon-owned `docs_index` collection
- they do **not** get written into `memory_entries`
- distilled institutional knowledge may later be extracted from docs, but raw
  corpus chunks remain outside the memory-confidence pipeline

---

## Owned Files

| File | Change |
|------|--------|
| `addons/docs-index/addon.yaml` | New manifest |
| `src/formicos/addons/docs_index/__init__.py` | New package marker |
| `src/formicos/addons/docs_index/indexer.py` | New chunker and reindex functions |
| `src/formicos/addons/docs_index/search.py` | New Queen tool handlers |
| `src/formicos/addons/docs_index/status.py` | New status-card endpoint |
| `tests/unit/addons/test_docs_index.py` | New addon tests |

---

## Do Not Touch

- `src/formicos/surface/addon_loader.py` - Wave 66 infrastructure already landed
- `src/formicos/surface/app.py` - addon route/panel mounting already landed
- `addons/codebase-index/` and `src/formicos/addons/codebase_index/` - use as reference only
- Any frontend files - panel rendering already exists
- `knowledge_catalog.py`, `projections.py`, `core/`, `engine/` - out of scope

---

## Repo Truth You Must Read First

Study these shipped references before writing code:

- `addons/codebase-index/addon.yaml`
- `src/formicos/addons/codebase_index/indexer.py`
- `src/formicos/addons/codebase_index/search.py`
- `src/formicos/addons/codebase_index/status.py`
- `tests/unit/addons/test_codebase_index.py`

Important repo-truth constraints:

- addon loader, panel registration, and addon routes are already live
- you should not need loader/runtime changes for this track
- status panels currently work with simple `status_card` payloads
- there is no existing replayed "last indexed at" field for addon-local state
- this addon is a corpus index, not a new institutional-memory ingestion path

So:

- do not invent a new event or projection just to track last indexed time
- a truthful status card with collection counts and collection name is enough
- do not route raw doc chunks through `memory_entries`

---

## Implementation Steps

### Step 1: Add the manifest

Create `addons/docs-index/addon.yaml`.

Follow the codebase-index structure closely:

```yaml
name: docs-index
version: "1.0.0"
description: "Semantic search over project documentation"
author: "formicos-core"

tools:
  - name: semantic_search_docs
    description: "Search documentation by meaning"
    handler: search.py::handle_semantic_search
    parameters:
      type: object
      properties:
        query:
          type: string
        top_k:
          type: integer
        file_pattern:
          type: string

  - name: reindex_docs
    description: "Rebuild or incrementally update the documentation index"
    handler: search.py::handle_reindex
    parameters:
      type: object
      properties:
        changed_files:
          type: array
          items:
            type: string

config:
  - key: doc_extensions
    type: string
    default: ".md,.rst,.txt,.html"
    label: "File extensions to index"
  - key: skip_dirs
    type: string
    default: "__pycache__,.git,node_modules,.venv,venv"
    label: "Directories to skip"

panels:
  - target: knowledge
    display_type: status_card
    path: /status
    handler: status.py::get_status

routes:
  - path: /status
    handler: status.py::get_status

triggers:
  - type: manual
    handler: indexer.py::incremental_reindex
```

Keep the first version manual-only. Do not add a cron trigger unless you find
an existing addon pattern that requires it for correctness.

### Step 2: Build `indexer.py`

Create `src/formicos/addons/docs_index/indexer.py`.

Required constants:

```python
COLLECTION_NAME = "docs_index"
DOC_EXTENSIONS = frozenset({".md", ".rst", ".txt", ".html"})
DEFAULT_SKIP_DIRS = frozenset({...})
```

Define a chunk dataclass:

```python
@dataclass
class DocChunk:
    id: str
    text: str
    path: str
    section: str
    line_start: int
    line_end: int
```

Implement:

- `chunk_document(content, file_path, *, suffix)`
- `_chunks_to_docs(chunks)`
- `full_reindex(workspace_path, vector_port, *, doc_extensions=None, skip_dirs=None)`
- `incremental_reindex(workspace_path, vector_port, *, changed_files=None, doc_extensions=None, skip_dirs=None)`

Chunking guidance:

- Markdown: split on `#`, `##`, `###` headings
- RST: split on heading underline patterns
- TXT: split on blank-line-delimited sections / paragraphs
- HTML: split on `<h1>` / `<h2>` / `<h3>` tags with a light regex heuristic

Metadata should include at least:

- `path`
- `section`
- `line_start`
- `line_end`
- `content`

Keep the implementation pragmatic. This does not need a full parser.

### Step 3: Build `search.py`

Create `src/formicos/addons/docs_index/search.py`.

Match the codebase-index handler style:

- `handle_semantic_search(...)`
- `handle_reindex(...)`

Requirements:

- use `runtime_context["vector_port"]`
- use `runtime_context["workspace_root_fn"]`
- return helpful strings, not raw dicts
- filter by `file_pattern` with `fnmatch` when provided
- query the `docs_index` collection only

Search result formatting should include:

- relative path
- section name
- line range
- semantic score
- truncated chunk preview

### Step 4: Build `status.py`

Create `src/formicos/addons/docs_index/status.py`.

Follow the codebase-index status-card pattern:

- call `vector_port.collection_info("docs_index")`
- return `display_type: "status_card"`
- include truthful items such as:
  - documents indexed / points count
  - collection name
  - supported extensions

Do not fabricate a "last indexed" timestamp if you do not have durable truth for it.

### Step 5: Keep the write set isolated

This track should land without any loader/runtime/frontend edits if the manifest
and package shape match the established addon pattern. If the addon does not
register cleanly, stop and verify the manifest or handler names before expanding
scope.

Future note, not in scope here:

- later Queen routing may choose between code/docs/data indices using addon
  capability metadata
- that future orchestration work should build on this addon rather than
  changing the addon into a memory-extraction path

---

## Tests

Create `tests/unit/addons/test_docs_index.py`.

Required tests:

1. `test_markdown_chunking_splits_on_headings`
2. `test_chunk_metadata_includes_section`
3. `test_handle_semantic_search_queries_docs_index`
4. `test_handle_reindex_indexes_docs_from_workspace`

Strongly recommended fifth test:

5. `test_status_endpoint_returns_status_card`

Use `tests/unit/addons/test_codebase_index.py` as the reference pattern.

---

## Acceptance Gates

1. `addons/docs-index/addon.yaml` loads without manifest errors
2. `semantic_search_docs` searches the `docs_index` collection
3. `reindex_docs` performs full or incremental reindex through the addon tool handler
4. Manual trigger points at `indexer.py::incremental_reindex`
5. Knowledge tab can render the docs-index status panel through the existing addon panel system
6. Doc chunks preserve section context in metadata
7. `docs_index` remains separate from `code_index`
8. No loader/runtime/frontend changes are required for the happy path

---

## Validation

Run before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Merge Order

This track is independent of Teams A and B and can merge at any time after the
Wave 67.5 prompts are dispatched.

---

## Track Summary Template

When done, report:

1. Which document formats were chunked in v1
2. Whether the addon loaded without any loader/runtime changes
3. What metadata is stored on each `DocChunk`
4. Whether the status card stayed truthful without inventing new state
5. Any small audit fixes found inside the owned files
