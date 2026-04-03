# Wave 86 Team B Prompt

## Mission

Make code structure traversable in the knowledge graph so retrieval can
benefit from MODULE nodes, DEPENDS_ON edges, and conservative
entry-to-module links.

This is the graph bridge phase-1 track.

## Owned Files

- `src/formicos/adapters/knowledge_graph.py` only if a new bridge
  predicate is clearly justified
- `src/formicos/addons/codebase_index/indexer.py`
- `src/formicos/addons/codebase_index/search.py` if needed for trigger-path
  context plumbing
- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/knowledge_catalog.py`
- relevant tests for codebase-index, structural reflection, KG bridge, and
  graph proximity

## Do Not Touch

- Team A learning files (`plan_patterns.py`, `planning_signals.py`,
  `planning_brief.py`, `queen_runtime.py`, `colony_manager.py`)
- frontend files
- playbook ranking / playbook-quality ideas
- broad app-startup plumbing unless strictly necessary

## Repo Truth To Read First

1. `structural_planner.py`
   `reflect_structure_to_graph()` already exists and creates MODULE nodes
   plus DEPENDS_ON edges.

2. `runtime.py`
   The current KG bridge only maps memory entries to SKILL/CONCEPT nodes
   and stores `entry_kg_nodes`.

3. `knowledge_catalog.py`
   Graph scoring currently reverse-maps PPR results through
   `entry_kg_nodes`, so code-structure nodes are not yet influencing
   retrieval meaningfully.

4. `addons/codebase_index/indexer.py` and `search.py`
   Manual and scheduled reindex already exist as real seams. Prefer a
   shared post-reindex helper instead of wiring only the manual trigger.

## What To Build

### 1. Wire graph reflection into the shared reindex seam

After successful reindex, call `reflect_structure_to_graph()` through the
existing runtime context.

Prefer a shared helper in the addon reindex path so both:

- manual/triggered reindex
- scheduled reindex

stay consistent.

### 2. Add conservative entry-to-module bridging

When memory entries are created, add MODULE links only from structured or
low-risk refs:

- source colony target files
- artifact filenames / paths
- exact file-path refs in title/summary

Do not mine arbitrary raw content with naive substring scans.

### 3. Keep the bridge edge small and truthful

If an existing predicate is sufficient, reuse it.

If a new bridge predicate is clearly better, keep it additive and
well-tested. Do not turn this into a graph-schema redesign.

### 4. Seed graph scoring from module refs

When a query references files/modules, resolve those MODULE nodes and use
them as graph seeds alongside the existing entry-based seeds.

This is the real retrieval payoff of the bridge.

### 5. Keep it best-effort

- no new event types
- no new frontend surface
- no semantic entity mining project
- reflection/bridge failures must not fail the reindex itself

## Constraints

- Do not put graph reflection in a random startup hook if the reindex seam
  can own it cleanly.
- Do not create a parallel persistent mapping unless repeated
  `resolve_entity()` calls are clearly too expensive.
- Do not depend on Team A changes.

## Validation

- tests for reflection after manual and scheduled reindex paths
- tests for conservative memory-entry -> MODULE edges
- tests showing non-zero graph-proximity influence for relevant
  file/module queries

Use the smallest targeted pytest set that proves the bridge works.

## Overlap Note

Team A may later consume graph-improved retrieval indirectly through
planning signals, but this track should not change planning-signal or
brief formatting itself.
