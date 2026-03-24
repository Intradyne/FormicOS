## Role

You own the replay surface, projection wiring, and operator-visible truth track
of Wave 44.

Your job is to:

- add the minimal event surface the Forager really needs
- wire projection state for domain strategy and cycle summaries
- update the core operator-facing docs so they describe the new capability
  honestly

This is the "make the Forager replayable and visible without event sprawl"
track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_44/wave_44_plan.md`
4. `docs/waves/wave_44/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/engine/tool_dispatch.py`
7. `src/formicos/engine/runner.py`
8. `src/formicos/core/events.py`
9. `src/formicos/surface/projections.py`
10. `src/formicos/core/types.py`
11. `docs/KNOWLEDGE_LIFECYCLE.md`
12. `docs/OPERATORS_GUIDE.md`
13. `CLAUDE.md`

## Coordination rules

- Add exactly **4** new event types. Not 5, not 7, not 10.
- Reuse `MemoryEntryCreated` for admitted forager entries.
- Do **not** add `KnowledgeCandidateProposed`.
- Search/fetch/rejection detail stays structured-log or telemetry material in
  v1 unless a real replay blocker proves otherwise.
- Keep docs aligned to the actual foundation wave, not the full reference
  architecture.
- Do **not** mutate existing event types unless a genuine blocker forces it.
- An `http_fetch` tool already exists and Wave 44 upgrades that seam rather
  than introducing a brand-new first HTTP capability. Keep the docs and event
  framing honest about that.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/core/events.py` | OWN | 4 new forager event types only |
| `src/formicos/surface/projections.py` | OWN | forager replay/projection state |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | explain forager candidate input path |
| `docs/OPERATORS_GUIDE.md` | MODIFY | operator controls and visibility |
| `CLAUDE.md` | MODIFY | current repo/wave truth as needed |
| `tests/unit/surface/` | CREATE/MODIFY | projection and replay tests |

## DO NOT TOUCH

- `src/formicos/adapters/egress_gateway.py` - Team 1 owns
- `src/formicos/adapters/fetch_pipeline.py` - Team 1 owns
- `src/formicos/adapters/content_quality.py` - Team 1 owns
- `pyproject.toml` - Team 1 owns dependency changes
- `src/formicos/adapters/web_search.py` - Team 2 owns
- `src/formicos/surface/forager.py` - Team 2 owns
- `src/formicos/surface/knowledge_catalog.py` - Team 2 owns trigger hook
- `src/formicos/surface/admission.py` - Team 2 owns admission bridge changes
- wave packet files after dispatch, unless explicitly asked for a docs-only fix

---

## Pillar 5: Event schema and projection state

### Required scope

Add exactly these event types:

1. `ForageRequested`
2. `ForageCycleCompleted`
3. `DomainStrategyUpdated`
4. `ForagerDomainOverride`

### Hard constraints

- Do **not** add search/fetch/rejection events in v1.
- Do **not** add a separate candidate-proposed event.
- Do **not** let the event surface grow just because the audit trail is
  interesting.

### Guidance

- Keep event payloads compact and replay-oriented.
- The replay state should focus on:
  - when/why a forage cycle was requested
  - what the cycle accomplished overall
  - what strategy the system learned for a domain
  - what operator domain overrides exist
- Team 2 will emit these events from the forager surface path. Make the schema
  easy to consume there.

---

## Projection and visibility guidance

### Required scope

1. Add projection handlers for the four new event types.
2. Expose enough summary state for operators to inspect foraging behavior.
3. Keep the visibility layer bounded and legible.

### Hard constraints

- Do **not** make projections depend on search/fetch log records becoming
  events.
- Do **not** claim the system has a richer audit surface than the code really
  ships.

### Guidance

- Domain-strategy summary and forage-cycle summary are the two highest-value
  projection surfaces.
- Docs should explain what the Forager can and cannot do in v1:
  - reactive first
  - bounded fetch levels
  - strict egress
  - no browser automation in the acceptance path
- Docs should also make it clear that the underlying HTTP tool already existed
  and is being tightened/upgraded under Wave 44, while the new replay surface
  stays limited to foraging state rather than raw fetch audit logs.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for event-schema and projection/replay seams
3. full `python -m pytest -q` if projection changes broaden across shared
   lifecycle surfaces

## Developmental evidence

Your summary must include:

- the exact 4 event types added
- what projection state now exists for foraging
- how `MemoryEntryCreated` was reused instead of adding a new proposal event
- what docs were updated to reflect the capability truthfully
- what event growth you explicitly rejected to keep this track bounded
