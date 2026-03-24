# Wave 51: Status

**Date:** 2026-03-20
**Status:** Complete. All three teams shipped. 3374 tests passing (3
pre-existing prompt line-count failures out of scope).

---

## What shipped

### Team 1: Replay Safety + Backend Truth

| Item | Status | Notes |
|------|--------|-------|
| `escalate_colony` replay safety (A1) | Shipped | `ColonyEscalated` event + projection handler; routing override survives replay |
| Queen note replay safety (A2) | Shipped | `QueenNoteSaved` event + projection handler; notes private (not visible chat); YAML kept as fallback |
| `dismiss-autonomy` classification (A5) | Shipped | Classified as intentionally ephemeral with inline documentation; recommendations regenerate each briefing cycle |
| Deprecated Memory API `Sunset` headers (C4) | Shipped | RFC 8594 `Sunset` + `Deprecation` headers + structlog usage logging |
| Config-override route documentation (C5) | Shipped | Documented as intentional: two routes serve different UX flows, same underlying event |
| `docs/REPLAY_SAFETY.md` (C6) | Shipped | Canonical replay-safety classification for all capabilities |
| Frozen-event comments (C7) | Shipped | `SkillConfidenceUpdated`, `SkillMerged`, `ContextUpdated` marked FROZEN |

### Team 2: Surface Truth + Visible Degradation

| Item | Status | Notes |
|------|--------|-------|
| Config-memory unavailable states (B1) | Shipped | Failed sections render muted "unavailable" placeholder; no-data shows "No configuration data yet" |
| Queen overview no-data states (B2) | Shipped | Federation shows "Unavailable" on failure vs "No peers configured" for empty; outcomes failure appends "outcomes unavailable" |
| Model/protocol freshness visibility (B3) | Shipped | Model registry shows "Updated Xs ago" + 60s auto-refresh; settings protocols show "Snapshot data -- refreshes on reconnect" |
| Briefing domain override actions (A7) | Shipped | Trust/distrust/reset buttons inline on domain chips; calls POST forager/domain-override and refreshes view |
| Strategy pills made visually inert (C9) | Shipped | Replaced with plain text label, no interactive affordance |
| Remove `fleet-view.ts` dead code (C1) | Shipped | File deleted, no remaining references |
| Rename operator-facing "Skill Bank" labels (C2) | Shipped | `skillBankStats` wire contract unchanged; no operator-facing "Skill Bank" text existed |
| Rename "Config Memory" surface (C3) | Shipped | Renamed to "Configuration Intelligence" in UI |

### Team 3: Vocabulary + Docs Truth

| Item | Status | Notes |
|------|--------|-------|
| AGENTS.md Wave 50 status correction | Shipped | Status note and Wave 50 section updated to reflect all items as landed |
| OPERATORS_GUIDE.md Wave 50 truth refresh | Shipped | Configuration Intelligence and Cross-Workspace Knowledge sections updated from "planned" to shipped |
| Memory/Knowledge naming bridge documented | Shipped | Single canonical explanation added to OPERATORS_GUIDE.md Knowledge System Overview |
| Wave 51 status handoff skeleton | Shipped | This file |
| OPERATORS_GUIDE.md "Config Memory" renamed to "Configuration Intelligence" | Shipped | Section heading and inline references updated |
| Phase 2 doc alignment | Shipped | REPLAY_SAFETY.md referenced in OPERATORS_GUIDE.md; event count updated 62 to 64; Wave 51 section added to AGENTS.md; final status completed |

---

## Stale audit findings correctly removed from scope

These UI audit findings (from `ui_audit_findings.md`) were initially flagged
but are not Wave 51 work because the backend substrate already landed in
Wave 50:

1. **F1 (Global scope UI)** -- Global promotion substrate is real. The
   `MemoryEntryScopeChanged` event carries `new_workspace_id`, projections
   handle global scope, and retrieval includes global entries. The "Promote
   to Global" button works as intended.

2. **F2 (Learned template badges)** -- Learned-template enrichment is real.
   `ColonyTemplateCreated` carries learned fields, `TemplateProjection` has
   success/failure counts, and `load_all_templates()` merges both sources.

---

## What stayed deferred

- Streaming fallback in `runtime.py` (`stream()` lacks the fallback chain
  that `complete()` has) -- runtime/reliability work, not polish
- Colony export ZIP streaming -- low severity, current usage is fine
- Agent Card versioning/cache control -- low severity
- Near-duplicate forager detection beyond SHA-256 -- future forager work

---

## Remaining debt classification

### Blockers

None.

### Surface-truth debt

Team 2 resolved all assigned surface-truth items. No remaining surface-truth
debt from Wave 51 scope.

### Docs debt

None. `docs/REPLAY_SAFETY.md` landed and referenced from OPERATORS_GUIDE.md.

### Follow-up debt

- 3 pre-existing test failures (queen prompt line-count assertions) --
  unrelated to Wave 51, existed before this wave
- Streaming fallback gap in `runtime.py` remains (runtime debt, not polish)

---

## Acceptance gate status

| Gate | Result | Notes |
|------|--------|-------|
| Gate 1: Escalation survives replay | PASS | `ColonyEscalated` event emitted; projection handler restores routing override |
| Gate 2: Queen notes survive replay | PASS | `QueenNoteSaved` event emitted; notes private, not visible in operator chat |
| Gate 3: Ephemeral capabilities are honest | PASS | `dismiss-autonomy` classified as intentionally ephemeral with inline docs |
| Gate 4: Visible capabilities are reachable | PASS | Briefing domain overrides wired inline; strategy pills made inert |
| Gate 5: Config-memory shows degraded state | PASS | Failed sections show "unavailable" placeholder |
| Gate 6: Queen overview explains absence | PASS | Federation/outcomes show explicit unavailable states |
| Gate 7: Model/protocol freshness is legible | PASS | 60s auto-refresh + "Updated Xs ago" + snapshot disclaimer |
| Gate 8: Dead/misleading artifacts removed | PASS | fleet-view.ts deleted; "Configuration Intelligence" label; strategy pills are text |
| Gate 9: Deprecated Memory API clearly deprecated | PASS | RFC 8594 Sunset + Deprecation headers + usage logging |
| Gate 10: Replay-safety classification exists | PASS | `docs/REPLAY_SAFETY.md` classifies all capabilities by durability tier |
| Gate 11: Historical naming explained once | PASS | Memory/Knowledge bridge documented in OPERATORS_GUIDE.md and REPLAY_SAFETY.md |
| Gate 12: Wave 50 landed truth preserved | PASS | AGENTS.md and OPERATORS_GUIDE.md updated; no regression |
| Gate 13: Product identity holds | PASS | No new subsystems, no new external dependencies, wave is subtractive |

---

## Replay-safety truth

`docs/REPLAY_SAFETY.md` is the canonical reference. Key classifications:

- **Event-sourced (durable):** All colony lifecycle, knowledge lifecycle,
  config changes, templates, approvals, forager cycles, and now escalation
  and Queen notes (Wave 51 additions).
- **File-backed (external):** Caste recipes, colony templates, system
  settings, workspace files. Queen notes YAML is backup only (event is
  source of truth).
- **Intentionally ephemeral:** Autonomy dismissals, config proposals
  (5min TTL), distillation candidates, competing hypothesis pairs.
- **Replay-derived (computed):** Colony outcomes, operator behavior signals,
  co-occurrence weights.
- **Frozen/legacy:** `SkillConfidenceUpdated`, `SkillMerged`,
  `ContextUpdated` -- exist for replay compatibility only.

---

## Scope notes

- Two new event types added: `ColonyEscalated`, `QueenNoteSaved` (union: 62 to 64)
- No new external dependencies
- No wire-contract renames
- All contract mirrors updated (events.py, ports.py, types.ts, frontend types.ts)
- 3374 tests passing
