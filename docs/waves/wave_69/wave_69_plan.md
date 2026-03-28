# Wave 69: The Product Surface

**Status:** Dispatch-ready packet
**Predecessor:** Wave 68
**Theme:** Make FormicOS usable by someone who isn't the builder. Take the
rich backend (hierarchy, provenance, PPR retrieval, deliberation frames,
plan persistence, session continuity, addon capabilities, workspace
taxonomy) and make it visible through progressive disclosure.

## Packet Authority

This file is the dispatch overview. The prompts are the authority for
implementation detail:

- `docs/waves/wave_69/team_a_prompt.md`
- `docs/waves/wave_69/team_b_prompt.md`
- `docs/waves/wave_69/team_c_prompt.md`

## Locked Boundaries

Wave 69 is a rendering wave, not an architecture wave.

- No new event types. No new projection fields.
- No changes to retrieval algorithms or scoring math.
- No new Queen tools. Wave 68 added the last batch.
- No addon development. No MCP integration changes.
- Backend changes are limited to: one new REST endpoint (unified search),
  one new REST endpoint (thread plan read), small metadata additions
  to `QueenMessage` emission, and a return-type change in
  `retrieve_relevant_memory()` to expose structured results.
- All new components follow `docs/design-system-v4.md` (Void Protocol).

## Scope

| Track | Outcome | Team | Dependency |
|-------|---------|------|------------|
| 1 | Inline colony progress cards in Queen chat | A | None |
| 2 | Consulted-sources chips on Queen responses | A | None |
| 3 | Inline diff preview on result/edit cards | A | None |
| 4 | Plan progress bar below chat tabs | A | Track 5 (plan read endpoint) |
| 5 | Thread plan read endpoint | A | None (backend) |
| 6 | Unified search endpoint (memory + addon indices) | B | None (backend) |
| 7 | Search-first knowledge UI with source-labeled results | B | Track 6 |
| 8 | Progressive disclosure toggle (detail mode) | B | None |
| 9 | Quick filters (source, domain, status pills) | B | None |
| 10 | Redesigned settings-view with card sections | C | None |
| 11 | System capability summary header | C | None |
| 12 | Inline editing with correct backend routing | C | None |

## Team Missions

### Team A — Enriched Queen Chat

Own the operator's primary interaction surface. Make the Queen chat show
what happened, not just that something happened. Inline colony progress,
consulted sources, diff previews, plan progress. One small backend addition:
thread plan read endpoint + consulted-entry metadata on QueenMessage.

### Team B — Unified Knowledge Search

Own the knowledge discovery surface. Search box first, tree view behind
a toggle. One backend endpoint that fans out to memory + addon indices
in parallel and returns source-labeled results. Results ranked within
source, grouped by source — no cross-source raw score sorting.

### Team C — Unified Settings & System Awareness

Own trust, config, and system legibility. One scrollable settings page
with card sections. Read from multiple backends, write only where an
existing endpoint/config path already exists. Read-only sections presented
clearly as read-only.

## Merge Order

All three teams can develop in parallel. No blocking dependencies between
teams. Recommended merge order:

1. Team A (most complex, touches the most files)
2. Team B (search endpoint + UI)
3. Team C (reorganization of existing surfaces)

## Global Do Not Touch

- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/knowledge_catalog.py` (retrieval math)
- `src/formicos/engine/` (any file)
- `config/caste_recipes.yaml` (Wave 68 just stabilized this)

## Design Standard

Every new component follows `docs/design-system-v4.md` (Void Protocol):

- Glass cards: `background: var(--v-surface)`, `border: 1px solid var(--v-border)`, `border-radius: 10px`
- Font stack: `var(--f-display)` for headings, `var(--f-body)` for text, `var(--f-mono)` for data/labels
- Accent: `var(--v-accent)` for interactive elements
- Confidence: `fc-dot` with status mapping (high=loaded, medium=pending, low=error)
- Animations: 0.15s transitions, `prefers-reduced-motion` respected

## Validation

```bash
npm run build        # frontend must build clean
npm run lint         # if lint config exists
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 69 succeeds if someone who isn't the builder can open FormicOS and:

- See what the Queen is doing without navigating to colony detail tabs
- Search across all knowledge sources from one box and understand where
  results came from
- Find and change any setting without knowing which backend stores it
- Understand at a glance what the system knows, what tools it has, and
  how it's configured
