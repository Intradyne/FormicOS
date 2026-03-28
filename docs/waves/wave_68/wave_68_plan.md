# Wave 68: The Strategic Queen

**Status:** Dispatch-ready packet
**Predecessor:** Wave 67.5
**Theme:** Make the Queen stateful, context-aware, and a better router across
institutional memory and addon-owned corpora.

## Packet Authority

This file is the dispatch overview. The prompts and ADR are the authority for
implementation detail:

- `docs/waves/wave_68/design_note.md`
- `docs/waves/wave_68/team_a_prompt.md`
- `docs/waves/wave_68/team_b_prompt.md`
- `docs/waves/wave_68/team_c_prompt.md`
- `docs/decisions/051-dynamic-context-caps.md`

`docs/waves/wave_68/addon_extension_contract.md` is retained as a compact
compatibility note only. The old long-form Wave 68 plan is superseded.

## Locked Boundaries

Wave 68 is intentionally flexible at the routing layer and conservative at the
memory layer.

- `memory_entries` remain distilled institutional knowledge only.
- Raw corpora stay in addon-owned indices and keep their own retrieval rules.
- The Queen is the router/composer across sources; colonies still work from
  injected context plus normal `memory_search`.
- Workspace taxonomy is soft guidance for routing, not hard validation.
- No new event types. No frontend work. No changes to core retrieval math.

## Scope

| Track | Outcome | Team | Dependency |
|------|---------|------|------------|
| 1 | Plan file persistence + `mark_plan_step` | A | None |
| 2 | Session continuity via `.formicos/sessions/` | A | Track 1 |
| 3 | Dynamic Queen context caps (ADR-051) | B | None |
| 4 | Deliberation frame with source-labeled routing context | B | Track 3; richer after Track 5 |
| 5 | Addon capability metadata + model-visible `list_addons` text | C | None |
| 6 | Soft workspace taxonomy + `set_workspace_tags` | C | Same packet as Track 5 |

## What Flexibility Means In Wave 68

This wave does **not** broaden the core knowledge model. It makes the system
more adaptable by improving the Queen's control plane:

- plans and session summaries are files, not memory entries
- addon manifests describe what each corpus index covers
- `list_addons` must surface that coverage in text the Queen can read
- the deliberation frame labels source types separately
- workspace tags bias routing without blocking novel concepts
- the Queen chooses when to search memory, search corpora, or refresh an index

That is the right flexibility seam: better routing and composition without
polluting institutional memory.

## Team Missions

### Team A

Own persistent Queen attention across sessions.

- write proposal plans to `.formicos/plans/{thread_id}.md`
- add `mark_plan_step`
- inject the plan at the bottom of `_build_thread_context()`
- write deterministic session summaries to `.formicos/sessions/{thread_id}.md`
- inject prior-session context on every `respond()` when the file exists

Hard boundary: do **not** touch `ThreadProjection.active_plan`. That field is
already used for `DelegationPlanPreview`.

### Team B

Own adaptive context sizing and pre-LLM deliberation support.

- add `queen_budget.py`
- compute budgets from `ModelRecord.context_window`
- reserve output with `_queen_max_tokens()`
- use `max(fallback, proportional)` so budgets never shrink below current
  behavior
- build a deliberation frame that labels institutional memory separately from
  addon-owned corpora and thread momentum

Hard boundary: no replay changes, no retrieval changes, no frontend changes.

### Team C

Own declarative routing metadata and workspace routing hints.

- extend `AddonManifest` with optional routing metadata
- update addon manifests with real capability values
- make `_list_addons()` return capability data in the text string the Queen
  reads
- surface the primary search path and, when the addon already exposes one, the
  primary refresh/index path
- add `set_workspace_tags`
- inject workspace tags near the top of `_build_thread_context()`
- add a Queen prompt rule that routes by source coverage instead of hardcoded
  addon names

Hard boundary: no projection or event changes; routing metadata must stay
backward-compatible.

## Merge Order

Recommended merge order:

1. Team A Track 1
2. Team B Track 3
3. Team C Tracks 5 and 6
4. Team A Track 2
5. Team B Track 4
6. Final truth pass across prompts/docs

Notes:

- Team B can build Track 4 before Team C lands, but final acceptance should
  happen after Track 5 so the addon coverage section reflects real capability
  metadata instead of only tool inventory.
- Team A and Team C both touch `_build_thread_context()` and
  `config/caste_recipes.yaml`, but the insertions are intentionally disjoint.

## Global Do Not Touch

- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/knowledge_catalog.py`
- frontend files

Wave 68 is a control-plane wave, not a schema-expansion wave.

## Acceptance Focus

- no use of `ThreadProjection.active_plan` for proposal-shaped data
- no `MemoryEntryCreated` path for plans or session summaries
- `context_window` read from `ModelRecord.context_window`
- output reserve derived from `_queen_max_tokens()`
- budget math uses `max(fallback, proportional)` in every slot
- deliberation frame is injected before the LLM call
- deliberation frame labels source types, especially addon-owned corpora
- `_list_addons()` text includes `content_kinds`, `path_globs`, search path,
  and any primary refresh/index path already exposed by the addon
- `set_workspace_tags` uses `field` / `old_value` / `new_value` and reads
  from `ws.config`
- no new event types

## Validation

```bash
pytest tests/unit/surface/test_plan_attention.py -v
pytest tests/unit/surface/test_session_continuity.py -v
pytest tests/unit/surface/test_queen_budget.py -v
pytest tests/unit/surface/test_deliberation_frame.py -v
pytest tests/unit/addons/test_addon_capability.py -v
pytest tests/unit/surface/test_workspace_taxonomy.py -v

ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 68 succeeds if the Queen becomes more capable without becoming blurrier:

- it remembers plans and sessions without polluting memory
- it scales gracefully from small to large context models
- it sees the workspace more clearly before deciding
- it routes across memory, docs, code, and future corpora with explicit source
  boundaries

That gives you a more flexible knowledge system by strengthening the Queen,
not by loosening the core memory model.
