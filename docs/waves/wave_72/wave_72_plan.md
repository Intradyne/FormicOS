# Wave 72: The Self-Governing System

Status: dispatch-ready packet
Predecessor: Wave 71.0 + 71.5
Theme: the system improves its own knowledge, learns from its own patterns,
continues work autonomously, and stays legible to the operator.

## Packet Authority

Use these docs:

- `docs/waves/wave_72/design_note.md` - four invariants
- `docs/waves/wave_72/team_a_prompt.md`
- `docs/waves/wave_72/team_b_prompt.md`
- `docs/waves/wave_72/team_c_prompt.md`
- `docs/waves/wave_72_polish_reference.md` - repo-truth polish reference

## Locked Boundaries

- No new event types.
- No retrieval/scoring changes.
- No `knowledge_catalog.py` changes.
- No new projection fields beyond what existing handlers already write.
- No new Qdrant collections or schema changes.
- No automatic knowledge correction.
- `app.py` remains the single scheduler seam for background work.
- Everything hangs off the existing action queue, operational state, and
  maintenance/autonomy infrastructure from Waves 70 and 71.

## Scope

| Track | Outcome | Team |
|-------|---------|------|
| 1 | Knowledge review scanning | A |
| 2 | Knowledge review processing | A |
| 3 | Knowledge health surface | A |
| 4 | Trigger fix + visible document ingest on active Knowledge tab | A |
| 5 | Continuation proposals | B |
| 6 | Scheduler consolidation | B |
| 7 | Cross-session warm start + idle execution | B |
| 8 | Workflow pattern recognition | C |
| 9 | Procedure suggestions | C |
| 10 | Product surface polish | C |
| 11 | Documentation refresh | C |

## Team Missions

### Team A - Knowledge Governance

Own the knowledge review lifecycle end to end:

- scan for problematic entries
- queue `knowledge_review` actions
- let the operator confirm / edit / invalidate
- expose knowledge health and visible document ingest on the active Knowledge
  tab

Also own the addon trigger fix and the active-surface ingest/reindex polish.

### Team B - Autonomous Continuation

Own the Queen's ability to continue work coherently across sessions and during
idle time.

This includes:

- continuation proposals
- warm-start continuation cues
- idle-time execution guard rails
- the single background scheduler order in `app.py`

### Team C - Workflow Learning + Product Polish + Documentation

Own:

- workflow-template proposals
- procedure suggestions
- writable-first Settings
- budget/autonomy persistence
- model admin
- nav cleanup
- docs refresh

## Shared Seams

### `app.py` operational sweep

Owner: Team B

Teams A and C provide pure helper functions. Team B wires the order.

Required order in the operational sweep:

1. `run_proactive_dispatch()` — capture briefing insights
2. Team A `scan_knowledge_for_review(...)` — receives briefing insights
3. Team B `queue_continuation_proposals(...)`
4. Team B `execute_idle_continuations(...)`
5. Team C `extract_workflow_patterns(...)`
6. Team C `detect_operator_patterns(...)`
7. existing approved-action processing / compaction

If proactive dispatch moves into `_operational_sweep_loop()`, the old daily
maintenance loop should remain responsible only for consolidation services.
Do not run the same proactive dispatch in both loops.

### `operations-inbox.ts`

Shared by Teams A and C.

- Team A adds `knowledge_review`
- Team C adds `workflow_template`
- Team C adds `procedure_suggestion`

Different `kind` values. Match the existing card/render pattern.

### `routes/api.py`

Shared across teams, additive only.

- Team A: review processing endpoint
- Team C: maintenance-policy route if needed
- Team C: model-admin route(s) if needed
- Team B: only add an endpoint if continuation truly cannot ride the existing
  `approve_action()` contract

### High-Value Verified Seams

These are the facts worth preserving across prompts:

- `build_operations_summary()` in `operations_coordinator.py` is the
  continuation candidate source.
- `knowledge_entry_usage` is separate from `memory_entries`.
- `approve_action()` already executes actions that carry
  `payload.suggested_colony`.
- the live active Knowledge tab is `knowledge-browser.ts`
- the existing upload/ingest flow is in `knowledge-view.ts`, which is not the
  active Knowledge tab
- both addon manual triggers are miswired to `incremental_reindex`
- `maintenance_policy` lives in `ws.config`
- `config-overrides` is not a trustworthy generic settings persistence seam

## Merge Order

```
Team B (scheduler + continuation) - merges first
Team A (knowledge governance)     - merges second
Team C (learning + polish)        - merges third
```

All three can build in parallel, but Team B owns the scheduler seam and should
land before final integration. Team C's docs refresh is the literal last merge.

## What Wave 72 Does Not Do

- no new event types
- no retrieval or scoring redesign
- no new knowledge storage layer
- no auto-correction of institutional memory
- no multi-user support

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
npm run build && npm run lint
```

## Success Condition

Wave 72 succeeds if:

- the system surfaces review-worthy knowledge through the action queue
- the operator can confirm, edit, or invalidate from the inbox flow
- the Queen proposes continuation naturally when a session resumes
- low-risk continuation work can execute while the operator is away
- successful multi-step patterns become reusable workflow-template proposals
- operator behavior can become procedure suggestions
- the active Knowledge tab has visible `Upload & Ingest` plus working reindex
  controls
- Settings is clearly writable-first
- budget/autonomy controls persist through a real route
- default model selectors hide hidden / no-key / unavailable models
- the Models admin surface can add and hide specific models
- addon reindex triggers actually work
- `CLAUDE.md` and `docs/AUTONOMOUS_OPERATIONS.md` reflect the real system
