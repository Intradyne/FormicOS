# Wave 69 — Team B: Unified Knowledge Search

**Theme:** Search box first, tree view behind a toggle. One question,
answers from everywhere — institutional memory, documentation, codebase —
labeled by source.

## Context

Read `docs/waves/wave_69/wave_69_plan.md` first. This is a rendering wave.
The backend search capabilities already exist — this wave wires them to a
unified frontend surface with one new REST endpoint for fan-out.

Read `CLAUDE.md` for hard constraints. Read `docs/design-system-v4.md` for
the Void Protocol design system.

## Your Files (exclusive ownership)

### Frontend
- `frontend/src/components/knowledge-browser.ts` — search-first redesign,
  detail mode toggle, quick filter pills
- `frontend/src/components/knowledge-search-results.ts` — **new**,
  source-grouped search result cards
- `frontend/src/types.ts` — search result types (additive only)

### Backend
- `src/formicos/surface/routes/knowledge_api.py` — unified search endpoint

### Tests
- `tests/unit/surface/test_unified_search.py` — **new**

## Do Not Touch

- `frontend/src/components/queen-chat.ts` — Team A owns
- `frontend/src/components/settings-view.ts` — Team C owns
- `frontend/src/components/model-registry.ts` — Team C owns
- `frontend/src/components/addons-view.ts` — Team C owns
- `src/formicos/surface/knowledge_catalog.py` — no retrieval changes
- `src/formicos/surface/projections.py` — no projection changes
- `src/formicos/core/events.py` — no new events
- `src/formicos/core/types.py` — no type changes
- `src/formicos/addons/codebase_index/` — do not modify addon code
- `src/formicos/addons/docs_index/` — do not modify addon code
- `config/caste_recipes.yaml` — stable from Wave 68

## Overlap Coordination

- Team A adds types to `types.ts`. Your additions are different types
  (search results). Additive, no conflict.
- Team A adds state to `store.ts`. You may add search result state.
  Different areas, additive.
- `formicos-app.ts` — Team C may adjust nav items. You don't touch the
  nav. The knowledge tab already exists. No conflict.
- `knowledge-view.ts` — You may need minor changes here if the tab
  container structure changes for the search-first layout. Coordinate:
  Team C does not touch this file.

---

## Track 6: Unified Search Endpoint

### Problem

The frontend has no single API call that searches across institutional
memory AND addon-owned indices. The existing `GET /api/v1/knowledge/search`
(knowledge_api.py:73) only queries `knowledge_catalog.search()`, which
hits institutional memory (vector store + legacy skill bank). Addon search
tools (`semantic_search_code`, `semantic_search_docs`) are only callable
via Queen tool dispatch or direct addon handler invocation.

### Implementation

**1. New endpoint in `knowledge_api.py`.**

```
GET /api/v1/workspaces/{workspace_id}/search?q=...&sources=memory,docs,code
```

Parameters:
- `q` (required): natural language query string
- `sources` (optional): comma-separated list of source types to search.
  Default: all available. Canonical values for this endpoint are
  `memory`, `docs`, and `code`. Map those stable UI tokens to addon
  capability metadata (`documentation`, `source_code`) internally.
- `limit` (optional): max results per source. Default 10, max 20.

**2. Fan-out logic.**

The endpoint needs access to:
- `knowledge_catalog` — for institutional memory search
- `runtime` — for addon handler resolution

Fan out in parallel using `asyncio.gather`:

```python
async def unified_search(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    query = request.query_params.get("q", "")
    if not query:
        return _err_response("QUERY_REQUIRED")
    sources_param = request.query_params.get("sources", "")
    limit = min(int(request.query_params.get("limit", "10")), 20)

    results: list[dict] = []
    tasks: list[Coroutine] = []

    # Always search institutional memory unless excluded
    requested = set(sources_param.split(",")) if sources_param else None
    if requested is None or "memory" in requested:
        tasks.append(_search_memory(query, workspace_id, limit))

    # Search addon indices based on capability metadata.
    # Use the actual app-state seam, not a fictional runtime.addon_registry.
    regs = getattr(request.app.state, "addon_registrations", [])
    if regs:
        for reg in regs:
            manifest = reg.manifest
            if not manifest.search_tool:
                continue
            if requested is not None:
                want_docs = "docs" in requested
                want_code = "code" in requested
                kinds = set(manifest.content_kinds or [])
                if not (
                    (want_docs and "documentation" in kinds)
                    or (want_code and "source_code" in kinds)
                ):
                    continue
            tasks.append(
                _search_addon(reg, query, workspace_id, limit)
            )

    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for batch in gathered:
        if isinstance(batch, list):
            results.extend(batch)
    return JSONResponse({"results": results, "total": len(results)})
```

**3. Memory search helper.**

```python
async def _search_memory(query, workspace_id, limit):
    items = await knowledge_catalog.search(
        query=query, workspace_id=workspace_id, top_k=limit,
    )
    return [
        {
            "source": "memory",
            "source_label": "Institutional Memory",
            "id": it.get("id", ""),
            "title": it.get("title", ""),
            "snippet": (it.get("summary") or it.get("content_preview") or "")[:200],
            "score": round(it.get("score", 0), 4),
            "metadata": {
                "confidence": round(it.get("confidence", 0.5), 2),
                "status": it.get("status", ""),
                "domains": it.get("domains", []),
                "sub_type": it.get("sub_type", ""),
            },
        }
        for it in items
    ]
```

**4. Addon search helper.**

Addon search handlers follow the signature in
`addons/codebase_index/search.py` and `addons/docs_index/search.py`:

```python
async def handle_semantic_search(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str
```

They return a formatted markdown string, not structured data. The unified
search endpoint must parse the markdown output into result items.

```python
async def _search_addon(reg, query, workspace_id, limit):
    manifest = reg.manifest
    addon_name = manifest.name

    # manifest.search_tool is the tool NAME (e.g., "semantic_search_code").
    # The handler REFERENCE lives in the matching tool spec's .handler field
    # (e.g., "search.py::handle_semantic_search").
    #
    # Two ways to call the handler:
    #
    # (a) Look up the tool name in manifest.tools to get the handler
    #     reference, then resolve via addon_loader._resolve_handler()
    #     and pass reg.runtime_context manually.
    #
    # (b) The tool handlers are already registered as wrapped callables
    #     in the Queen's tool dispatcher during addon loading
    #     (addon_loader.py:262). Those wrappers have runtime_context
    #     baked into the closure. If you have access to the queen's
    #     tool dispatcher, call it directly.
    #
    # For the REST endpoint, path (a) is cleaner because the route
    # doesn't hold a Queen reference:

    tool_spec = next(
        (t for t in manifest.tools if t.name == manifest.search_tool),
        None,
    )
    if tool_spec is None:
        return []

    from formicos.surface.addon_loader import _resolve_handler
    try:
        handler = _resolve_handler(addon_name, tool_spec.handler)
    except Exception:
        return []

    # The registration object stores the runtime_context that was
    # injected during loading (addon_loader.py:224).
    rc = getattr(reg, "runtime_context", {}) or {}

    raw = await handler(
        {"query": query, "top_k": limit},
        workspace_id, "",  # thread_id not needed for search
        runtime_context=rc,
    )

    # Parse markdown results into structured items
    return _parse_addon_results(
        raw, addon_name, manifest.content_kinds, limit,
    )
```

The addon search results come back as markdown like:
```
**path/to/file.py:10-25** (score: 0.832)
\`\`\`
code content here
\`\`\`
```

Parse with a simple regex to extract path, line range, score, and content
snippet. Each result becomes:

```python
{
    "source": addon_name,  # e.g., "codebase-index"
    "source_label": manifest.description or addon_name,
    "id": f"{addon_name}:{path}:{line_start}",
    "title": path,
    "snippet": content[:200],
    "score": parsed_score,
    "metadata": {
        "file_path": path,
        "line_range": f"{line_start}-{line_end}",
        "content_kinds": manifest.content_kinds,
    },
}
```

**5. Runtime context construction.**

Check how `queen_tools.py` builds `runtime_context` when calling addon
handlers. Replicate the same pattern. The key fields are typically:
- `vector_port` — for vector search
- `data_dir` — workspace data directory
- `workspace_id`

Look at `addon_loader.py` handler resolution (lines 86–125) for the
pattern. The tool registry wrapper injects `runtime_context` if the
handler signature accepts it.

**Important:** The addon handler resolution and `runtime_context` wiring
must match the existing pattern. Do not invent a new calling convention.
Read `queen_tools.py`'s addon tool dispatch to find the exact seam.

**6. Ranking within source, not across sources.**

Do NOT sort all results by raw score across sources. Memory scores, code
search scores, and doc search scores are not comparable — they come from
different scoring functions with different distributions.

Return results grouped by source. Each source group is sorted by score
descending (within that source). The frontend renders groups separately.

The response shape:

```json
{
  "results": [
    {"source": "memory", "source_label": "Institutional Memory", ...},
    {"source": "memory", ...},
    {"source": "codebase-index", "source_label": "Index and search...", ...},
    {"source": "docs-index", "source_label": "Index and search...", ...}
  ],
  "total": 15
}
```

Results are ordered: all memory results first (sorted by score), then
each addon group (sorted by score). The frontend groups by `source` for
display.

### Tests

Create `tests/unit/surface/test_unified_search.py` with at least:

1. `test_unified_search_returns_memory_results` — mock knowledge_catalog,
   query, assert memory results in response with correct shape.
2. `test_unified_search_fans_out_to_addons` — mock addon registry with
   a search_tool, assert addon handler called through the real
   addon-registration seam.
3. `test_unified_search_filters_by_source_param` — request
   `?sources=memory`, assert addon handlers not called.
4. `test_unified_search_parses_addon_markdown` — feed markdown output,
   assert structured result items extracted.
5. `test_unified_search_handles_addon_failure_gracefully` — addon handler
   raises, assert memory results still returned.
6. `test_results_grouped_by_source` — assert results arrive in source
   groups, not interleaved by raw score.

---

## Track 7: Search-First Knowledge UI

### Problem

The knowledge browser (knowledge-browser.ts) defaults to a flat catalog
list with tree view, score breakdown bars, Beta posteriors, and provenance
timelines. That's a power-user tool. An end user wants a search box.

### Current state of knowledge-browser.ts

The component already has:
- `_queryText` state for search input
- `_filterType` for skill/experience filtering
- `_sortBy` for newest/confidence/relevance
- `_threadFilter` for scope filtering
- Sub-view modes: `catalog` | `graph` | `tree`
- Entry card rendering with confidence display, badges, relationships
- Score breakdown bar with 7 segments

The search input exists but it queries the existing
`/api/v1/knowledge/search` endpoint (institutional memory only). The
results render in the same detailed card format.

### Implementation

**1. Redesign the default view.**

Replace the current default (catalog list) with a search-first layout:

- **Large centered search box** at the top. Prominent, full-width within
  the content area. Placeholder: "Search knowledge, docs, code..."
  Style: glass card background, 14px body font, accent border on focus.
- **Quick stats below the search box** (before any search): entry count,
  domain count, addon index status (if available from addon health data).
  One line, muted text, `var(--f-mono)`.
- **Results area** below, initially empty. Shows source-grouped results
  after a search.

**2. Wire to unified search endpoint.**

On search input (debounced, 300ms), call:
```
GET /api/v1/workspaces/${wsId}/search?q=${query}&limit=10
```

Group results by `source` field and render in labeled sections:

- **"From Institutional Memory"** — memory entries with:
  - Title (linked to detail view)
  - Content snippet (2 lines max)
  - Confidence indicator: `fc-dot` with tier mapping
    (`>= 0.7` → loaded, `>= 0.4` → pending, else → error).
    Show "High" / "Medium" / "Low" text label, NOT alpha/beta numbers.
  - Domain badges
  - Status badge (verified/candidate/active)

- **"From Documentation"** — doc results with:
  - File path as title (linked to workspace browser)
  - Section name if available
  - Content snippet (2–3 lines)
  - Score indicator (simple bar, not 7-segment breakdown)

- **"From Codebase"** — code results with:
  - File path + line range as title
  - Code snippet in monospace (`var(--f-mono)`)
  - Language indicator if detectable from file extension

Each section is a glass card. Section headers use `var(--f-display)`,
11px, `var(--v-fg-muted)`, uppercase.

If a source returns no results, omit that section (don't show "No results
from Documentation").

**3. New component `knowledge-search-results.ts`.**

Extract the search result rendering into its own component to keep
`knowledge-browser.ts` manageable. Props:

```typescript
@property({ type: Array }) results: UnifiedSearchResult[] = [];
@property() activeWorkspaceId = '';
```

Renders the source-grouped cards. Emits `entry-selected` custom event
when a memory entry is clicked (so the parent can switch to detail view).
Emits `file-selected` custom event when a doc/code result is clicked
(so the parent can navigate to workspace browser).

---

## Track 8: Progressive Disclosure Toggle

### Problem

The existing tree view, score breakdown bars, Beta posteriors, provenance
timeline are valuable for the builder but overwhelming for new users.

### Implementation

**1. Add a "Detail Mode" toggle.**

In the knowledge browser header area (where sub-view mode buttons
currently live), add a toggle switch labeled "Detail Mode" or a single
icon toggle (magnifying glass → list icon).

- **Off (default):** Search-first view from Track 7. Entry cards show
  simple confidence indicator (high/medium/low + `fc-dot`), title,
  snippet, domain badges. No score breakdown bar, no Beta numbers, no
  provenance timeline.
- **On:** Full power-user view. The existing catalog/tree/graph modes
  become available. Score bars, Beta posteriors, provenance timelines,
  relationships — everything currently rendered.

Store the toggle state in component local state (`@state()`). Do not
persist it — default to off on every page load. This reinforces
"simple by default."

**2. Conditional rendering in entry cards.**

When rendering entry cards, check the detail mode state:

```typescript
${this._detailMode ? this._renderDetailCard(entry) : this._renderSimpleCard(entry)}
```

`_renderSimpleCard` is the new simplified rendering.
`_renderDetailCard` is the existing `_renderEntryCard` logic (renamed).

---

## Track 9: Quick Filters

### Problem

The current knowledge browser has dropdown-based filtering. Dropdowns
are discoverable but slow. Filter pills are more tactile and show the
active filter state at a glance.

### Implementation

**1. Filter pill strip below the search box.**

Three pill groups, horizontally arranged:

- **Source:** All | Memory | Docs | Code
  - "All" is default (no filter). Others filter the unified search
    `sources` parameter.
  - Only show pills for sources that actually exist. If no docs-index
    addon is installed, don't show "Docs."

- **Domain:** Dynamically populated from knowledge hierarchy top-level
  branches. Show up to 6 domain pills. If more than 6, show a "More..."
  pill that opens a dropdown.
  - Domain filtering is client-side: filter `results` by
    `metadata.domains` containing the selected domain.

- **Status:** All | Verified | Candidate
  - Client-side filter on `metadata.status`.

**2. Pill styling.**

Use the `fc-pill` atom if one exists, otherwise create simple pill
styles:

```css
.filter-pill {
  padding: 4px 10px;
  border-radius: 12px;
  font-family: var(--f-mono);
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  background: var(--v-surface);
  border: 1px solid var(--v-border);
  cursor: pointer;
  transition: all 0.15s;
}
.filter-pill[active] {
  background: var(--v-accent-muted);
  border-color: var(--v-accent);
  color: var(--v-accent-bright);
}
```

**3. Filter state.**

Filters persist during the session (component state). Changing a filter
re-triggers the search with updated parameters. Source filter changes the
`sources` query param. Domain and status filters are applied client-side
to the fetched results.

---

## Empty States

- **No search query yet:** Show quick stats + gentle prompt: "Search
  across all knowledge sources."
- **Search with no results:** "No results for '{query}'" with suggestion
  to try broader terms or check addon index status.
- **No knowledge entries at all (fresh workspace):** "No knowledge yet.
  Start a conversation with the Queen to build institutional memory."
- **Addon index not available:** Don't show that source's pill. If all
  addon indices are unavailable, search falls back to memory only.

---

## Types to Add (in `types.ts`)

```typescript
/** Wave 69: unified search result from /search endpoint. */
export interface UnifiedSearchResult {
  source: string;           // 'memory' | 'codebase-index' | 'docs-index'
  source_label: string;     // human-readable source name
  id: string;               // entry ID or composite key
  title: string;
  snippet: string;
  score: number;
  metadata: Record<string, unknown>;  // source-specific metadata
}
```

---

## Acceptance Gates

- [ ] Unified search endpoint returns source-labeled results
- [ ] Endpoint fans out to memory + addon indices in parallel
- [ ] Addon handler failures don't break the entire search
- [ ] Results are ranked within source, not across sources
- [ ] Search-first UI is the default knowledge browser view
- [ ] Results grouped by source with clear section labels
- [ ] Confidence shown as high/medium/low, not alpha/beta numbers
- [ ] Detail mode toggle switches between simple and power-user view
- [ ] Detail mode defaults to off on page load
- [ ] Quick filter pills for source, domain, status
- [ ] Source pills reflect actually-installed addons
- [ ] All new components follow Void Protocol design system
- [ ] No changes to retrieval algorithms or scoring math
- [ ] No new event types

## Validation

```bash
npm run build
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
pytest tests/unit/surface/test_unified_search.py -v
```
