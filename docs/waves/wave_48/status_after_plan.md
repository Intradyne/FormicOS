## Wave 48 Status After Integration

**Date:** 2026-03-19  
**Status:** Substantially accepted. The thread timeline, colony-audit Forager
enrichment, cross-surface navigation, running-state clarity, and caste
grounding are landed in the repo. The main remaining gap is preview-flow
integration: the frontend attempts a dedicated preview API route, but the
backend substrate still exposes preview through Queen tool paths rather than a
matching REST endpoint.

---

## What shipped

### Team 1: Backend Enrichment

| Item | Status | Notes |
|------|--------|-------|
| Thread timeline API | Shipped | `GET /api/v1/workspaces/{ws}/threads/{thread}/timeline` in `api.py` backed by `build_thread_timeline()` |
| Thread timeline read model | Shipped | Chronological replay-safe entries for colony, queen/operator, workflow, forage, and knowledge events |
| Colony audit Forager enrichment | Shipped | `build_colony_audit_view()` now cross-references Forager provenance and linked forage cycles |
| `ForageCycleSummary` linkage | Shipped | Preserves `colony_id`, `thread_id`, `gap_domain`, and `gap_query` from `ForageRequested` |
| Preview response shaping | Shipped | `spawn_colony(preview=true)` and `spawn_parallel(preview=true)` return richer structured preview fields |
| `request_forage` mediated substrate | Shipped | TOOL_SPEC, category mapping, runner handler, runtime callback, and synchronous Forager execution path landed |

### Team 2: Frontend Flow + Integration

| Item | Status | Notes |
|------|--------|-------|
| Thread timeline component | Shipped | `thread-timeline.ts` renders chronological audit entries with filtering and expandable details |
| Thread timeline integration | Shipped | `thread-view.ts` embeds a collapsible thread-scoped timeline section |
| Cross-surface navigation | Shipped | Timeline -> colony detail, timeline -> knowledge browser, colony audit -> knowledge browser |
| Colony audit Forager display | Shipped | Forager badge, provenance fields, source URL links, and forage-cycle details render in `colony-audit.ts` |
| Running-state clarity | Shipped | `colony-detail.ts` now shows a bounded "Latest Activity" block for running colonies |
| Review step preview UX | Partial | Frontend attempts backend preview fetch with graceful fallback to local estimates |

### Team 3: Recipes + Docs Truth

| Item | Status | Notes |
|------|--------|-------|
| Reviewer recipe grounding | Shipped | Reviewer now has read-only workspace + git inspection tools |
| Researcher recipe grounding | Shipped | Researcher now has workspace read tools plus `http_fetch` for targeted URL lookups |
| Queen minimal-colony-first guidance | Shipped | Recipe guidance now recommends `fast_path` / single-agent starts for simple tasks |
| AGENTS.md updated | Shipped | Post-Wave 48 tool surface and grounded-specialist guidance reflected |
| OPERATORS_GUIDE.md updated | Shipped | Grounded Specialists section documents Reviewer/Researcher posture and tradeoffs |

---

## Important nuance

### Researcher fresh-information path

Two things are true at once:

- The **mediated** `request_forage` substrate is implemented in the engine and
  runtime.
- The **currently exposed** Researcher recipe still uses the simpler
  `http_fetch` fallback for targeted external lookups.

So the preferred mediated path is no longer "not implemented"; it is
implemented but not yet enabled in the shipped Researcher recipe.

### Preview flow

The frontend colony creator now attempts a dedicated preview fetch before
launch. However, the current frontend route target (`/api/v1/preview-colony`)
does not correspond to a matching REST endpoint in `api.py`. The UI therefore
falls back cleanly to local estimates, but the end-to-end "real preview truth
via frontend API" flow is still incomplete.

---

## What remains

| Item | Status | Notes |
|------|--------|-------|
| Review step real preview API integration | Partial | Backend preview substrate exists, but the frontend fetch target does not yet match a live REST route |
| Researcher recipe exposure of `request_forage` | Deferred | Substrate exists; recipe/docs still prefer `http_fetch` fallback |
| Demo preparation / capture | Deferred | Not required for substrate acceptance |

---

## Acceptance gate status

| Gate | Result |
|------|--------|
| Gate 1: Reviewer Is Grounded But Still Read-Only | PASS |
| Gate 2: Researcher Is Grounded And Has Truthful Fresh-Info | PASS (fallback exposed, mediated path implemented but not enabled) |
| Gate 3: Thread Timeline Is Real | PASS |
| Gate 4: Colony Audit Carries Forager Attribution | PASS |
| Gate 5: Preview Confirmation Uses Real Preview Truth | PARTIAL |
| Gate 6: The Operator Story Is Connected | PASS |
| Gate 7: Running-State Clarity Stays Bounded | PASS |
| Gate 8: Product Identity Holds | PASS |
| Gate 9: Docs And Recipes Match Reality | PARTIAL |
| Gate 10: Follow-On Measurement Remains Interpretable | PASS |

---

## Scope notes

- No new event types were added; the event union remains at 62.
- The timeline and audit surfaces are read-model/projection work, not a new
  event stream.
- The Forager remains service-backed; Wave 48 did not convert it into a normal
  in-colony worker.
- The main docs-truth nuance is not "did Wave 48 land?" but "which
  fresh-information and preview paths are exposed versus merely implemented in
  substrate."

---

## Post-wave measurement note

Wave 48 changes an important confound: caste grounding. Follow-on measurement
should explicitly isolate:

- old castes vs grounded castes
- fast path vs colony
- knowledge off vs on
- foraging off vs on

Without that ablation, changes in the compounding curve will be hard to
interpret honestly.
