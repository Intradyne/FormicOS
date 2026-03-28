# Wave 68 Design Note: Three Architectural Invariants

**Date:** 2026-03-25
**Status:** Locked - all Wave 68 tracks must respect these boundaries.

## Invariant 1: `memory_entries` for distilled knowledge only

The institutional memory pipeline (`memory_entries` projection, Qdrant
`memory` collection, Thompson Sampling, co-occurrence, confidence evolution)
is reserved for distilled knowledge: skills, experiences, patterns,
conventions, and bug reports.

**What does NOT enter `memory_entries`:**
- Session state (plan files, session summaries)
- Raw indexed corpora (code chunks, documentation chunks)
- Operational snapshots (colony logs, deployment state)

**Why:** Entries in `memory_entries` receive Beta posteriors, participate in
Thompson Sampling retrieval, accumulate co-occurrence weights, and undergo
confidence reinforcement from colony outcomes. Mixing operational state into
this pipeline would pollute institutional knowledge with ephemeral noise,
inflate co-occurrence graphs, and make confidence scores meaningless.

**How it applies to Wave 68:**
- Track 1 (plan attention): Plans live in `.formicos/plans/{thread_id}.md`,
  read from disk, never enter `memory_entries`.
- Track 2 (session continuity): Session summaries live in
  `.formicos/sessions/{thread_id}.md`, injected via file read, never enter
  `memory_entries`.

## Invariant 2: New content shapes enter through addon-owned indices

Each content domain gets its own addon with its own Qdrant collection:
- Code chunks -> `codebase-index` addon -> `code_index` collection
- Doc chunks -> `docs-index` addon -> `docs_index` collection
- Future data/spec indexers -> their own addons and collections

**The core retrieval model (`knowledge_catalog.py`) is not touched.**
It serves `memory_entries` only. Addon search tools handle their own
collections.

**Why:** Knowledge entries carry rich metadata (Beta posteriors, decay
classes, provenance, co-occurrence, hierarchy paths) that corpus chunks do
not have. Mixing them in one retrieval pipeline would require either
degrading the metadata model or bolting on fake posteriors for chunks.
Separate indices keep each domain's retrieval semantics clean.

**How it applies to Wave 68:**
- Track 5 (addon capability metadata): Addons declare `content_kinds`,
  `path_globs`, and `search_tool` so the Queen can route across sources
  without cross-index retrieval.

## Invariant 3: The Queen is the router/composer across sources

Colonies search `memory_entries` via `memory_search`. The Queen searches
everything - knowledge, code, docs, external tools - via addon tools during
deliberation and plan composition, then injects curated results into colony
context via task descriptions.

**No automatic cross-index retrieval.** The Queen decides what to search,
combines results, and passes relevant context to colonies. This keeps the
retrieval pipeline simple and gives the Queen explicit control over what
evidence informs each colony's work.

Routing is explicit in two dimensions:

- **search** - which source should answer this question?
- **refresh/index** - which addon should update coverage for this corpus?

Source labels matter. The Queen should see institutional memory, code/doc
corpora, and workspace hints as different evidence classes, not as one blob.

**How it applies to Wave 68:**
- Track 4 (deliberation frame): The frame includes source-labeled addon
  coverage so the Queen knows which addons can search or refresh what
  content.
- Track 5 (capability metadata): `list_addons` output includes
  `content_kinds` and `search_tool` so the Queen can route queries. Existing
  addon handlers/triggers can surface the refresh path without a new core
  type.
- Track 6 (workspace taxonomy): Tags bias the Queen's routing decisions,
  not the retrieval algorithm. They are soft hints, not hard validation.
