# Wave 85 Team A Prompt

## Mission

Make the structural signal actually fire for real operator phrasing and
make saved-pattern rendering truthful enough to debug.

This is the planning-signal quality track. Team B owns live routing-policy
wiring and the eval harness.

## Owned Files

- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_structural_planner.py` if needed

## Do Not Touch

- `src/formicos/surface/planning_policy.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/eval/*`
- `pyproject.toml`
- frontend files
- graph-bridge or KG adapter code outside your owned files

## Repo Truth To Read First

1. `src/formicos/surface/planning_signals.py`
   `_fetch_coupling()` already calls `get_structural_hints()`.
   `_fetch_saved_patterns()` already exists and already does
   deterministic bundle matching.

2. `src/formicos/surface/planning_brief.py`
   already renders playbook, worker, coupling, and saved-pattern lines.
   The issue is truthfulness and usefulness, not missing plumbing.

3. `src/formicos/surface/structural_planner.py`
   `get_structural_hints()` already works off `code_analysis`.
   The weakest seam is `_find_mentioned_files()`, which is still too
   exact-match oriented for phrases like "workspace roots".

4. `tests/eval/test_planning_ablation.py`
   currently assumes route stability across configs. Team B will change
   that. Do not edit eval assumptions from this track.

## What To Build

### 1. Improve structural seed extraction

In `_find_mentioned_files()`:

- normalize file paths, stems, and operator message text into a shared form
- treat `_`, `-`, `.`, `/`, and whitespace as equivalent separators
- allow phrase-style matches such as:
  - `workspace roots` -> `workspace_roots.py`
  - `plan patterns` -> `plan_patterns.py`
  - `queen runtime` -> `queen_runtime.py`

Keep this deterministic and lightweight. This is not fuzzy search.

### 2. Make structural suppression reasons inspectable

When the structural signal is absent, distinguish at least:

- no structural/file indicators in the message
- structural indicators present but no file matches
- file matches found but confidence suppressed

You can encode this in the hint dict and/or logs, but tests must be able
to assert on the reason without scraping human prose.

### 3. Keep the coupling signal compact and truthful

Do not dump huge group/file payloads into the brief or metadata.

The brief should stay compact, but it should be possible to see whether
the structural line was absent because:

- the planner found nothing relevant
- the planner matched files but suppressed a weak hint

### 4. Fix saved-pattern rendering

Do not show `q=0.00` when the matched pattern simply lacks
`outcome_summary.quality`.

Preferred rendering shape:

- always show `match_score`
- show `q=` only when an outcome quality is actually present
- include small match-basis cues when available, for example:
  `task-class`, `complexity`, `files`

Examples:

- `Saved: workspace-roots-refactor (match=0.70, 1 colony, task-class+files)`
- `Saved: auth-refactor (match=0.80, q=0.87, 3 colonies, files)`

### 5. Add focused tests

Add/adjust tests for:

- phrase-style structural seeding
- explicit suppression-reason behavior
- saved-pattern rendering when outcome quality is missing
- saved-pattern rendering when outcome quality is present

## Constraints

- Do not rebuild saved-pattern retrieval. It already exists.
- Do not wire `reflect_structure_to_graph()` in this track.
- Do not change eval harness files.
- Do not expand Queen metadata with full saved-pattern payloads.

## Validation

- `python -m pytest tests/unit/surface/test_planning_signals.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- any new structural-planner unit tests you add

## Overlap Note

Team B will reread your final signal shape before landing the live routing
and eval updates. Keep field names explicit and compact so they can score
them cleanly.
