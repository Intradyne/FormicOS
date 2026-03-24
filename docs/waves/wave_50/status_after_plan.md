# Wave 50: Status

**Date:** 2026-03-20
**Status:** Complete. All three teams shipped. Backend substrate, global scope,
template surfaces, and reliability hardening are landed and tested.

---

## What shipped

### Team 1: Configuration Memory + Reliability Backend

| Item | Status | Notes |
|------|--------|-------|
| `spawn_source` field on ColonySpawned | Shipped | Additive field, backward-compatible default `""` |
| Learned-template fields on ColonyTemplateCreated | Shipped | `learned`, `task_category`, `max_rounds`, `budget_limit`, `fast_path`, `target_files_pattern` |
| `new_workspace_id` on MemoryEntryScopeChanged | Shipped | Additive field, `""` = global scope |
| TemplateProjection enrichment | Shipped | success_count, failure_count cross-derived from colony outcomes |
| Template consumer merge (disk + projection) | Shipped | `load_all_templates()` merges disk YAML + projection-derived learned templates |
| Auto-template on qualifying colony completions | Shipped | Quality >= 0.7, rounds >= 3, spawn_source == "queen", no duplicate category+strategy |
| Task classifier integration | Shipped | Category-first lookup in preview and auto-template |
| Global scope in projections | Shipped | `_on_memory_entry_scope_changed` sets scope="global" and clears workspace_id |
| Two-phase retrieval (workspace then global) | Shipped | `memory_store.search()` with `include_global` param, 0.9x discount for global entries |
| Knowledge promotion route (workspace->global) | Shipped | `promote_entry` accepts `target_scope="global"` |
| Knowledge listing scope filter | Shipped | API accepts `scope` query param; catalog includes global entries in workspace listings |
| Circuit breaker: per-request retry cap | Shipped | `max_retries_per_request` (default 3) on `_ProviderCooldown` |
| Circuit breaker: cooldown notify callback | Shipped | `notify_callback` fires on cooldown activation |
| SQLite PRAGMA mmap_size | Shipped | 256 MB mmap_size on init |
| SQLite PRAGMA busy_timeout upgrade | Shipped | 15000ms (was 5000ms) |
| Workspace-scoped template API endpoint | Shipped | `GET /api/v1/workspaces/{id}/templates` returns merged operator + learned templates |
| Wave 50 backend tests | Shipped | 28 targeted tests in test_wave50_team1.py |
| Contract mirrors | Shipped | events.py, types.ts, frontend types.ts all updated |

### Team 2: Cross-Workspace Knowledge Frontend + Template UX

| Item | Status | Notes |
|------|--------|-------|
| Preview card template annotation | Shipped | Nested `template` object with name, learned/operator badge, W/L stats |
| Config-memory template surface | Shipped | Fetches from `/api/v1/workspaces/{id}/templates`, renders learned + operator |
| Knowledge browser global scope | Shipped | Scope badges (Thread/Workspace/Global), "Promote to Global" button, "Global Only" filter |
| Promotion candidate display | Shipped | `promotion_candidate: true` entries show hint badge |
| Store global scope handling | Shipped | Tracks global promotions and template stats from events |
| PreviewCardMeta type updated | Shipped | `template?` field added to types.ts |

### Team 3: Recipes + Docs + Measurement

| Item | Status | Notes |
|------|--------|-------|
| Queen recipe: template suggestion guidance | Shipped | Updated "How to respond" step 1 |
| Configuration memory docs (OPERATORS_GUIDE.md) | Shipped | Operator-authored vs learned distinction |
| Cross-workspace knowledge docs (OPERATORS_GUIDE.md) | Shipped | Retrieval order, promotion rules |
| Phase 0 measurement matrix | Shipped | 5-dimension ablation protocol |
| AGENTS.md Wave 50 section | Shipped | Architectural truth documented |

---

## Acceptance gate status

| Gate | Result |
|------|--------|
| Gate 1: Learned templates are replay-safe | PASS -- ColonyTemplateCreated carries all learned fields, TemplateProjection rebuilt on replay |
| Gate 2: Template consumers merge both sources | PASS -- `load_all_templates()` merges disk + projection, disk wins on ID collision |
| Gate 3: Template matching informs preview | PASS -- Category-first lookup populates nested `template` object in preview metadata |
| Gate 4: Auto-template qualification is conservative | PASS -- Quality, rounds, spawn_source, dedup gates all enforced |
| Gate 5: Global knowledge scope exists | PASS -- Additive field, projection handler, workspace_id cleared, scope filter in catalog |
| Gate 6: Promotion is operator-controlled | PASS -- Thread->workspace and workspace->global both work |
| Gate 7: Auto-promotion candidates flagged | PASS -- Frontend shows hint badge for `promotion_candidate: true` entries |
| Gate 8: Circuit breaker prevents cost runaway | PASS -- Per-request retry cap with early break, notify callback |
| Gate 9: SQLite pragmas upgraded | PASS -- mmap_size=256MB, busy_timeout=15000ms |
| Gate 10: Product identity holds | PASS -- No external dependencies introduced |
| Gate 11: Docs and recipes match reality | PASS -- This status file reflects landed state |

## Scope notes

- No new event types added (union remains at 62)
- No new external dependencies
- All changes are additive fields on existing events
- 3349+ tests passing (3 pre-existing prompt line-count failures out of scope)
