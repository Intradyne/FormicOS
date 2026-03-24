# Wave 49: Status

**Date:** 2026-03-20
**Status:** Accepted after cleanup pass. All three teams complete plus
integrator cleanup. Chat-first orchestration surface shipped end-to-end:
structured metadata emission, preview and result cards, ask/notify distinction,
compact header, confirm-from-params dispatch, and deterministic Queen thread
compaction. Inline adjust deferred.

---

## What shipped

### Team 1: Backend Message Enrichment

| Item | Status | Notes |
|------|--------|-------|
| `QueenMessage` metadata fields (intent, render, meta) | Shipped | Additive optional fields in `core/events.py`, replay-safe |
| `QueenMessageProjection` metadata passthrough | Shipped | `projections.py` passes intent/render/meta to frontends |
| `_emit_queen_message()` enhanced signature | Shipped | Accepts optional intent, render, meta parameters |
| Contract mirrors updated | Shipped | `docs/contracts/events.py`, `docs/contracts/types.ts`, `frontend/src/types.ts` |
| `PreviewCardMeta` / `ResultCardMeta` types | Shipped | Defined in both backend contracts and frontend types |
| Frontend store metadata handling | Shipped | `store.ts` checks for and passes through Wave 49 metadata |
| Preview metadata emitted on Queen messages | Shipped | `respond()` detects preview actions, emits camelCase `PreviewCardMeta` payload |
| Result metadata emitted on follow-up messages | Shipped | `follow_up_colony()` emits camelCase `ResultCardMeta` payload |
| Ask/notify classification in runtime | Shipped | `notify` for preview proposals and completions; `ask` pinning in compactor |
| Queen thread compaction | Shipped | Deterministic: 6000-token budget, 10-message recent window, pinned asks + active previews, structured-metadata-first summary block |
| Wave 49 backend tests | Shipped | `test_wave49_queen_metadata.py` — 17 tests |

### Team 2: Chat Components + Layout

| Item | Status | Notes |
|------|--------|-------|
| `fc-preview-card.ts` component | Shipped | Task, team shape, strategy, fast-path badge, cost, target files, Confirm/Cancel/Open Full Editor |
| `fc-result-card.ts` component | Shipped | Status (color-coded), rounds, cost, quality, entries, validator, Colony Detail + Timeline links |
| Cards rendered in `queen-chat.ts` | Shipped | Renders `preview_card` and `result_card` inline when render metadata present |
| Ask/notify visual distinction | Shipped | Ask: left-border accent + "needs input" badge. Notify: reduced opacity. Heuristic fallback for `?` |
| Chat-first default layout | Shipped | `chatExpanded` defaults to `true`, dashboard via "Show Dashboard" toggle |
| Compact status header | Shipped | Running count, session cost, active plans, knowledge count |
| Confirm/cancel dispatch from stored params | Shipped | `confirm-preview` dispatches via `spawn_colony`, visible thread confirmation |
| Card types in `frontend/src/types.ts` | Shipped | `PreviewCardMeta`, `ResultCardMeta` interfaces, metadata on `QueenChatMessage` |
| Store metadata passthrough | Shipped | `store.ts` passes intent/render/meta from events |
| Result card navigation | Shipped | Colony Detail and Timeline buttons (Audit removed — was identical to Colony Detail) |
| Bounded inline adjust controls | Deferred | "Open Full Editor" escape hatch provides drill-down path |

### Team 3: Recipes + Docs + Polish

| Item | Status | Notes |
|------|--------|-------|
| Queen recipe: chat-first orchestration guidance | Shipped | Preview-first, ask-vs-notify, compact results |
| Queen recipe: preview-first dispatch guidance | Shipped | "preview first, then spawn on confirmation" |
| Queen recipe: post-completion summaries | Shipped | Compact conversational summaries, don't dump events |
| AGENTS.md updated | Shipped | Status note, Wave 49 feature section with landed/not-landed |
| OPERATORS_GUIDE.md updated | Shipped | Conversational Colony section with operator flow and honest status |
| Wave 49 status docs | Shipped | This file |
| CLAUDE.md | No changes needed | No stale Wave 49 claims |

### Cleanup / Integrator Pass

| Item | Status | Notes |
|------|--------|-------|
| Snapshot parity: intent/render/meta on Queen threads | Fixed | `view_state.py` `_build_queen_threads` now includes metadata — cards survive refresh/reconnect |
| Preview meta normalized to `PreviewCardMeta` shape | Fixed | `build_colony_preview()` outputs camelCase; `respond()` strips internal keys, adds threadId/workspaceId |
| Result meta normalized to `ResultCardMeta` shape | Fixed | `follow_up_colony()` outputs camelCase with maxRounds, entriesExtracted, validatorVerdict, threadId |
| Confirm-flow compatibility | Fixed | `commands.py` accepts `team` as alias for `castes`, forwards `targetFiles` and `fastPath` to `runtime.spawn_colony` |
| Audit navigation honesty | Fixed | Removed duplicate "Audit" button (was identical to Colony Detail); Colony Detail + Timeline remain |
| Status docs truth | Fixed | This file updated to reflect actual state |

## What was deferred

| Item | Reason |
|------|--------|
| Bounded inline adjust | Deferred — "Open Full Editor" escape hatch provides drill-down |
| Selective progress notify rows | Not implemented |

## Acceptance gate status

| Gate | Result |
|------|--------|
| Gate 1: Preview/result cards survive refresh and reconnect | PASS — snapshot now includes intent/render/meta |
| Gate 2: Preview/result cards receive values in the contract shape frontend reads | PASS — camelCase `PreviewCardMeta` and `ResultCardMeta` shapes |
| Gate 3: Confirm-preview dispatches with same team/fastPath/targetFiles as previewed | PASS — `team` accepted as alias, `fastPath`/`targetFiles` forwarded |
| Gate 4: Backward compatibility for older QueenMessage logs | PASS — fields are additive, optional, defaults to None |
| Gate 5: Docs/status no longer overclaim | PASS — this file |

## Scope notes

- No new event types added (union remains at 62)
- No new adapters or subsystems
- No new external dependencies
- The only contract change is additive optional fields on `QueenMessage`

## Follow-on work

1. **Inline adjust controls** — currently deferred in favor of "Open Full Editor" escape hatch
2. **Selective progress notify rows** — bounded progress summaries in chat
