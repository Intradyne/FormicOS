# Track C: Documentation Truth — Status After Team 1/2

**Date:** 2026-03-19
**Status:** Team 1 and Team 2 work landed. Docs truth pass in progress.

---

## What landed

- **Team 1 (Forager Operator Surface)** — fully landed:
  - Forager API endpoints: `POST .../forager/trigger`, `POST .../forager/domain-override`,
    `GET .../forager/cycles`, `GET .../forager/domains`
  - Web-source badge in knowledge browser frontend (entries with `source_colony_id === 'forager'`
    show provenance: source URL, domain, credibility, quality score, fetch timestamp)
  - OTel wiring in app startup (conditional via `FORMICOS_OTEL_ENABLED` env var)
  - Forager activity surfacing in proactive-briefing component
  - ForagerService fully wired with EgressGateway, FetchPipeline, WebSearch adapter chain

- **Team 2 (Eval Harness)** — substantially landed:
  - Clean-room workspace isolation: `ws_id = f"seq-{suite_id}-{run_id}"` with UUID-based run_id
  - `knowledge_attribution` populated from projection truth via `_build_attribution()`
  - `ExperimentConditions` includes `knowledge_mode`, `foraging_policy`, `random_seed`,
    `run_id`, `git_commit`, `config_hash`
  - Run manifest written as separate JSON file beside results
  - Three task suites: `pilot.yaml` (3 tasks), `full.yaml` (10 tasks), `benchmark.yaml` (13 tasks)
  - CLI supports `--knowledge-mode` and `--foraging-policy` args
  - Compounding curve analysis with `compute_curves()` generating raw, cost, time, and cumulative curves

## What remains deferred

- **Multi-run statistical analysis** (bootstrap CIs, paired comparisons) — not implemented.
  Analysis templates are ready to consume this when it lands, but do not claim it exists.
- **Measurement data** — no real eval runs have been executed yet. Analysis templates,
  demo scaffolds, and the publication checklist are ready but unfilled.

---

## Docs updates completed in this pass

| Doc | Update |
|-----|--------|
| `docs/OPERATORS_GUIDE.md` | Removed "Operator-trigger UI surface" from deferred list. Added note about forager API endpoints. |
| `docs/waves/wave_46/compounding_curve_analysis.md` | Removed stale `knowledge_persistence` field (duplicate of `knowledge_mode`). |
| `docs/waves/wave_46/run_review_checklist.md` | Replaced `knowledge_persistence` with `knowledge_mode` (2 occurrences). |
| `docs/waves/wave_46/demo_audit.md` | Updated web-source badge and forager cycle history from "Pending Team 1" to "Exists". Removed Team 1 gating note from forager-sourced provenance section. |

## Docs updates NOT made (and why)

| Doc | Why no change |
|-----|---------------|
| `README.md` | Already updated in Wave 45 Team 3 with 62-event references and web foraging feature. Current content is truthful. |
| `docs/KNOWLEDGE_LIFECYCLE.md` | Already states "Reactive, proactive, and operator-triggered foraging are operational." No stale claims found. |
| `CLAUDE.md` | Already lists forager-related key paths. No stale claims found. |

## What will need updating after measurement data exists

| Doc | Update needed |
|-----|---------------|
| `README.md` | Add measurement results reference (only if publication checklist passes). |
| Wave 46 report docs | Fill analysis templates from real data. |
| Demo scaffolds | Replace placeholder notes with actual run references. |

---

## Principle applied

From the coder prompt:

> Do not fabricate measurements.
> Do not write benchmark claims before the data exists.
> Do not overclaim "publication-ready" if only a pilot exists.
> Keep the product identity ahead of the benchmark story.

Track C docs truth is now current with landed code. Measurement data
does not exist yet — analysis templates remain unfilled scaffolds,
not claims.
