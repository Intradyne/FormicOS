# Wave 33.5 Team 2 — Retrieval Context Enrichment

## Role

You are adding metadata annotations to search results so agents can see confidence tiers, decay classes, federation sources, and colony outcomes. This is ~40 lines of formatting code that changes agent behavior without architectural changes. No new events, no new dependencies.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `engine/runner.py` | MODIFY | Annotate memory_search results with confidence tier |
| `surface/runtime.py` | MODIFY | Annotate transcript_search results with quality + extraction count |
| `tests/unit/engine/test_search_enrichment.py` | CREATE | Confidence tier annotation tests |
| `tests/unit/surface/test_transcript_enrichment.py` | CREATE | Transcript result annotation tests |

## DO NOT TOUCH

- `config/caste_recipes.yaml` — Team 1 owns
- `surface/knowledge_catalog.py` — Wave 33 Track A owns (no active changes, but avoid conflict)
- `surface/projections.py` — no changes needed, read-only access for projection data
- Any file in `core/` or `adapters/`
- Any file in `surface/routes/`

---

## Task 2a: Annotate memory_search results with confidence tier

### Where

`engine/runner.py` — `_handle_memory_search()` at line 388. The catalog results are formatted at lines 460-482. Currently:

```
Catalog results:
  --- System Knowledge ---
  [i] [SOURCE] {title}: {preview[:400]}
```

### Implementation

After the catalog results are built (line 446), annotate each result before formatting:

```python
def _confidence_tier(item: dict[str, Any]) -> str:
    """Classify confidence tier from Bayesian posteriors."""
    alpha = item.get("conf_alpha", 5.0)
    beta = item.get("conf_beta", 5.0)
    total_obs = alpha + beta - 10  # subtract prior
    status = item.get("status", "candidate")
    ci_width = 0.0
    if alpha + beta > 2:
        # Approximate CI width: 2 * sqrt(alpha*beta / ((alpha+beta)^2 * (alpha+beta+1)))
        n = alpha + beta
        ci_width = 2.0 * (alpha * beta / (n * n * (n + 1))) ** 0.5
    prediction_errors = item.get("prediction_error_count", 0)
    age_days = _age_in_days(item.get("created_at", ""))

    if prediction_errors > 3 or age_days > 90:
        return "STALE"
    if total_obs > 20 and ci_width < 0.15 and status == "verified":
        return "HIGH"
    if total_obs > 5 and status in ("verified", "active"):
        return "MODERATE"
    if total_obs > 0 and status == "candidate":
        return "LOW"
    return "EXPLORATORY"

def _format_confidence_annotation(item: dict[str, Any]) -> str:
    """Build the confidence annotation line."""
    tier = _confidence_tier(item)
    alpha = item.get("conf_alpha", 5.0)
    beta = item.get("conf_beta", 5.0)
    obs = int(alpha + beta - 10)
    parts = [f"Confidence: {tier} ({obs} observations)"]

    decay_class = item.get("decay_class", "ephemeral")
    if decay_class != "ephemeral":
        parts.append(f"({decay_class})")

    # Check for foreign observations (federation)
    crdt = item.get("observation_crdt")
    if crdt and isinstance(crdt, dict):
        instances = set()
        for counter in ("successes", "failures"):
            counts = crdt.get(counter, {}).get("counts", {})
            instances.update(counts.keys())
        if len(instances) > 1:
            parts.append("(includes peer data)")

    return "  " + " ".join(parts)
```

**Enriched format:**
```
Catalog results:
  --- System Knowledge ---
  [i] [SOURCE] {title}: {preview[:400]}
      Confidence: HIGH (47 observations) (stable)
```

The `conf_alpha`, `conf_beta`, `status`, `decay_class`, and `prediction_error_count` fields are available on the result dicts returned by `knowledge_catalog.search()`. The catalog builds these from the projection's `memory_entries` dict (projections.py lines 753+).

**Important:** The catalog search results (returned by `make_catalog_search_fn()` at runtime.py:1037) are `list[dict[str, Any]]`. The confidence fields (`conf_alpha`, `conf_beta`) need to be included in the catalog's result dicts. Check if `knowledge_catalog.py`'s `_search_thread_boosted()` already includes these — the KnowledgeItem dict structure (lines 29-47) has a `confidence` field (the posterior mean) but may not have `conf_alpha`/`conf_beta` separately. If not, add them to the result dict construction.

### Handling missing fields

If `conf_alpha`/`conf_beta` aren't in the result dict, fall back:
```python
alpha = item.get("conf_alpha", item.get("confidence", 0.5) * 10)  # rough approximation
beta = item.get("conf_beta", (1 - item.get("confidence", 0.5)) * 10)
```

But prefer adding the fields to the catalog result dict if they're readily available from the projection.

---

## Task 2b: Annotate transcript_search results with outcome

### Where

`surface/runtime.py` — `make_transcript_search_fn()` at line 1107. Results formatted at lines 1197-1202. Currently:

```
[Colony {cid[:8]} ({status})] Task: {task[:100]}
  Output snippet: {snippet[:200]}
  Artifacts: {count} ({types})
```

### Implementation

The `ColonyProjection` has `quality_score` and `skills_extracted` fields. Add them to the formatted output:

```python
# At the result formatting section (line 1197):
quality = colony_proj.quality_score if hasattr(colony_proj, "quality_score") else None
skills = colony_proj.skills_extracted if hasattr(colony_proj, "skills_extracted") else 0

status_str = status
if quality is not None:
    status_str = f"{status}, quality: {quality:.2f}"

knowledge_line = ""
if skills > 0:
    knowledge_line = f"\n  Knowledge extracted: {skills} entries"

# Format:
# [Colony {cid[:8]} ({status}, quality: 0.87)] Task: {task[:100]}
#   Output snippet: {snippet[:200]}
#   Artifacts: {count} ({types})
#   Knowledge extracted: 3 entries
```

If `quality_score` or `skills_extracted` aren't directly on the projection object, check the `ColonyCompleted` event fields — `skills_extracted` is there (events.py line 232). The projection should have it. Search for where it's set in `projections.py`.

---

## Tests

### test_search_enrichment.py

```python
def test_confidence_tier_high():
    item = {"conf_alpha": 30.0, "conf_beta": 7.0, "status": "verified", "created_at": "2026-03-01T00:00:00"}
    assert _confidence_tier(item) == "HIGH"

def test_confidence_tier_exploratory():
    item = {"conf_alpha": 6.0, "conf_beta": 5.0, "status": "candidate", "created_at": "2026-03-15T00:00:00"}
    assert _confidence_tier(item) == "EXPLORATORY"

def test_confidence_tier_stale():
    item = {"prediction_error_count": 5, "conf_alpha": 20.0, "conf_beta": 5.0, "status": "verified", "created_at": "2025-12-01T00:00:00"}
    assert _confidence_tier(item) == "STALE"

def test_annotation_includes_decay_class():
    item = {"conf_alpha": 15.0, "conf_beta": 5.0, "status": "active", "decay_class": "stable", "created_at": "2026-03-10T00:00:00"}
    annotation = _format_confidence_annotation(item)
    assert "(stable)" in annotation

def test_annotation_federation_source():
    item = {
        "conf_alpha": 15.0, "conf_beta": 5.0, "status": "active",
        "created_at": "2026-03-10T00:00:00",
        "observation_crdt": {"successes": {"counts": {"inst-a": 5, "inst-b": 3}}, "failures": {"counts": {}}},
    }
    annotation = _format_confidence_annotation(item)
    assert "(includes peer data)" in annotation

def test_annotation_default_ephemeral_not_shown():
    item = {"conf_alpha": 15.0, "conf_beta": 5.0, "status": "active", "decay_class": "ephemeral", "created_at": "2026-03-10T00:00:00"}
    annotation = _format_confidence_annotation(item)
    assert "(ephemeral)" not in annotation
```

### test_transcript_enrichment.py

```python
def test_transcript_result_includes_quality():
    # Mock a colony projection with quality_score=0.87
    # Verify formatted result contains "quality: 0.87"

def test_transcript_result_includes_knowledge_count():
    # Mock a colony projection with skills_extracted=3
    # Verify formatted result contains "Knowledge extracted: 3 entries"

def test_transcript_result_missing_quality_graceful():
    # Colony projection without quality_score
    # Verify no crash, quality line omitted
```

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

**Layer check:** `engine/runner.py` is in the engine layer. The `_confidence_tier()` function must NOT import from surface. All data comes from the result dict (passed in from the surface layer via callbacks). This is fine — the function is pure computation on dict fields.
