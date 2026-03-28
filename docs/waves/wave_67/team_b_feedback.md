# Wave 67.0 — Team B: Domain Normalization + Outcome-Confidence Reinforcement

**Tracks:** 2 (Domain Normalization), 3 (Rank Credit + ESS Cap)
**Mission:** Fix two knowledge feedback loop problems. (1) Domain tags drift
because extraction doesn't suggest existing domains. (2) Outcome confidence
gives equal credit to all retrieved entries regardless of rank, and alpha/beta
can grow unbounded. No new event types. No core model changes.

---

## Coordination Context

- `CLAUDE.md` defines the evergreen repo rules (4-layer architecture,
  69-event closed union, Pydantic v2, Beta posteriors).
- This prompt is the authority for Team B's scope. If `AGENTS.md` conflicts
  with this prompt, this prompt wins for this dispatch.
- Team A works in parallel on Track 1 (projections.py hierarchy fields,
  memory_store.py, hierarchy.py, routes/api.py, knowledge-browser.ts,
  bootstrap script). No file overlap with Team B.
- **Merge order:** Team A merges first. Team B rebases on Team A's landing.
  Team B's work is fully independent — rebase is for cleanliness, not
  because of code dependencies.

---

## ADR Reference

- `docs/decisions/049-knowledge-hierarchy.md` — Context on hierarchy design.
  Team B does not implement hierarchy, but the domain normalization in Track 2
  prevents orphan hierarchy branches from forming.
- No dedicated ADR for Track 2 or Track 3. These are implementation
  refinements within the existing knowledge metabolism framework (ADR-039).

---

## Owned Files

| File | Action | Est. Lines |
|------|--------|------------|
| `src/formicos/surface/memory_extractor.py` | Inject existing domain suggestions into extraction prompt | ~15 |
| `src/formicos/surface/colony_manager.py` | Rank-based credit + ESS cap in `_hook_confidence_update` | ~25 |
| `src/formicos/engine/scoring_math.py` | New `rescale_preserving_mean` helper | ~12 |
| `tests/unit/surface/test_domain_normalization.py` | **New file** — domain suggestion tests | ~40 |
| `tests/unit/engine/test_scoring_math_ess.py` | **New file** — ESS cap tests | ~50 |

---

## Do Not Touch

- `core/types.py` — No new fields on any model.
- `core/events.py` — No new events. The 69-event union is closed.
- `projections.py` — Team A owns hierarchy additions.
- `memory_store.py` — Team A owns Qdrant payload changes.
- `knowledge_catalog.py` — Retrieval changes are Wave 67.5 scope.
- `queen_runtime.py` — Queen orchestration, not in scope.
- `queen_tools.py` — Queen tools, not in scope.
- `routes/api.py` — Team A owns new endpoints.
- `knowledge-browser.ts` — Team A owns tree view.

---

## Track 2: Domain Normalization at Extraction Time

### Problem

Domain tags drift without constraint. The same concept gets multiple names:
"python_testing", "python_test_patterns", "testing_python". The existing
`_normalize_domain()` (memory_extractor.py:31–33) handles case/whitespace
but not semantic equivalence. With hierarchy in place (Track 1), drift
creates orphan branches that should be the same node.

### Implementation

#### Step 1: Inject domain suggestions into extraction prompt

In `memory_extractor.py`, `build_extraction_prompt()` (line 88).

The function signature (line 88–93) includes `existing_entries: list[dict[str, Any]] | None = None`.
These are entries retrieved from the knowledge catalog before extraction.

After line 94 (the three-path branch for prompt construction), before the
prompt string is assembled, extract unique domain tags from existing entries
and inject them as guidance:

```python
# Wave 67: domain normalization via existing entry suggestion
existing_domains: set[str] = set()
if existing_entries:
    for e in existing_entries[:10]:
        for d in e.get("domains", []):
            existing_domains.add(d)

# Add to prompt (in the domain field instruction section):
domain_hint = ""
if existing_domains:
    sorted_domains = sorted(existing_domains)[:20]
    domain_hint = (
        "\nUse one of these existing domain tags if applicable "
        "(do not create synonyms): "
        + ", ".join(sorted_domains)
    )
```

Append `domain_hint` to the prompt after the three-path branch (lines 133–205)
completes, near line 206 where `parts.append()` assembles the final prompt.
This ensures the hint applies to all three prompt paths. Look for where the
`domains` field schema is described — the hint should appear just before or
after that section.

**Key constraints:**
- Cap at 20 domains to avoid prompt bloat
- Cap at 10 existing entries to limit iteration
- Keep the hint as guidance, not a hard constraint — if none of the existing
  domains match, the LLM should still freely name a new one
- Do NOT modify `_normalize_domain()` or `_normalize_domains()` — those
  functions are fine as-is

#### Step 2: Verify existing_entries is populated

Check the call sites of `build_extraction_prompt()`. Verify that
`existing_entries` is actually passed with real data. If it's always `None`
at the call site, the domain hint will never fire. Trace the caller chain
and confirm existing entries are retrieved before extraction.

If the call site doesn't pass existing entries, that's a pre-existing gap —
note it in your track summary but don't expand scope to fix it (that would
touch files outside your ownership).

---

## Track 3: Outcome-Confidence Reinforcement with Rank Credit

### Problem

`_hook_confidence_update()` (colony_manager.py:1476) gives equal credit to
all accessed entries regardless of retrieval rank. The #1 result and the #10
result get the same alpha/beta delta. This dilutes the reinforcement signal.

Additionally, there is no effective sample size cap. Alpha+beta can grow
unbounded, making high-evidence entries increasingly resistant to confidence
updates over time — eventually they become immovable.

### ADR-049 Reference

The ESS cap at 150 is documented in ADR-049's `compute_branch_confidence`
function. Team B implements the same cap at the individual entry level in
the outcome confidence path. The math is identical: rescale alpha and beta
proportionally to cap total ESS while preserving the posterior mean.

### Implementation

#### Step 1: Add `rescale_preserving_mean()` to scoring_math.py

In `src/formicos/engine/scoring_math.py` (79 lines total, `exploration_score`
at line 32). Add a new function:

```python
def rescale_preserving_mean(
    alpha: float, beta: float, max_ess: float = 150.0,
) -> tuple[float, float]:
    """Rescale Beta parameters to cap effective sample size.

    Mathematically equivalent to exponential decay with gamma = 1 - 1/max_ess.
    Default cap of 150 (not 100) lets high-evidence entries stabilize
    without becoming immovable. 100 would be too aggressive per production
    Thompson Sampling literature (Russo et al. recommend N_eff ≈ 200 for
    nonstationary environments).

    Preserves the posterior mean: alpha/(alpha+beta) is unchanged.
    """
    ess = alpha + beta
    if ess <= max_ess:
        return alpha, beta
    scale = max_ess / ess
    return alpha * scale, beta * scale
```

This is Engine layer — pure computation, no Surface imports. The layer
boundary is correct: `engine/` may not import from `surface/`.

#### Step 2: Rank-based credit assignment in colony_manager.py

In `_hook_confidence_update()` (line 1476). The current code at line 1542:

```python
delta_alpha = min(max(0.5 + quality_score, 0.5), 1.5)
```

And line 1562:

```python
delta_beta = min(max(0.5 + failure_penalty, 0.5), 1.5)
```

These apply the same delta to every accessed entry. The access records in
`colony.knowledge_accesses` preserve item order — items within each access
dict maintain their ranked retrieval position.

**Read the access record structure carefully** before modifying. Look at:
- How `knowledge_accesses` is populated (search for `KnowledgeAccessRecorded`
  event handler in projections.py, line ~1566)
- What shape each access record has (it's a list of dicts, each with an
  `"items"` key or similar — verify the actual field name)
- Whether item order corresponds to retrieval rank

Once you understand the structure, apply geometric credit:

```python
# Geometric credit: 0.7^rank (Position-Based Model examination probabilities)
# Yields [1.0, 0.7, 0.49, 0.34, 0.24, ...] — models declining attention
# better than harmonic 1/(rank+1) per production recommendation system
# findings (Udemy, Scribd).
credit = 0.7 ** rank  # rank is 0-indexed position within the access items

if succeeded:
    base_delta = min(max(0.5 + quality_score, 0.5), 1.5)
    delta_alpha = base_delta * credit
else:
    base_delta = min(max(0.5 + failure_penalty, 0.5), 1.5)
    delta_beta = base_delta * credit
```

**Rank tracking with dedup:** The existing loop (lines 1501–1506) has a
dedup guard that skips already-seen item IDs. Use `enumerate()` on the
items list within each trace. The raw enumerate index is the correct rank —
deduped items should still consume a rank slot since they occupied a
retrieval position.

**Important:** The existing code iterates over accessed entries. Read the
code between lines 1476 and 1620 to understand the full loop structure
before modifying. The access records are structured: each trace has an
`"items"` list preserving retrieval order.

#### Step 3: ESS cap after confidence update

After computing `new_alpha` and `new_beta` (lines 1543, 1564), apply the
ESS cap before emitting the `MemoryConfidenceUpdated` event (line ~1573):

```python
from formicos.engine.scoring_math import rescale_preserving_mean

# Cap effective sample size at 150
new_alpha, new_beta = rescale_preserving_mean(new_alpha, new_beta)
```

This import is legal: Surface may import from Engine.

**Placement:** The actual code flow in the success path is:

1. Line 1542: `delta_alpha` computed
2. Line 1543: `new_alpha = decayed_alpha + delta_alpha`
3. Lines 1547–1556: mastery restoration bonus added to `new_alpha`
4. Line 1565: `new_confidence` computed from `new_alpha / (new_alpha + new_beta)`
5. Line 1572: `MemoryConfidenceUpdated` event emitted
6. Line 1592: auto-promotion check

The ESS cap must go AFTER step 3 (mastery restoration) but BEFORE step 4
(confidence computation). Insert between line 1556 and line 1565. In the
failure path, insert between line 1564 (`new_beta` assignment) and line 1565.

#### Step 4: Verify mastery restoration still works

The mastery restoration logic (lines 1547–1556) adds a 20% gap-recovery
bonus when `current_alpha < peak_alpha * 0.5` for stable/permanent entries.
After ESS capping, `peak_alpha` tracking still needs to work correctly.

Check that `peak_alpha` is tracked on the projection entry (it is — see
projections.py line 1677 in `_on_memory_confidence_updated`). The projection
handler sets `peak_alpha = max(peak, e.new_alpha)` — and since the ESS cap
is applied before emission, `e.new_alpha` is the **post-cap** value. This
means `peak_alpha` tracks the capped peak, not the theoretical uncapped peak.

This is the correct behavior: mastery restoration checks
`decayed_alpha < peak_alpha * 0.5`, and since both the current value and the
peak are in the same capped space, the comparison remains meaningful. No
additional tracking needed.

---

## Tests

### Track 2 tests — `tests/unit/surface/test_domain_normalization.py`

1. **`test_extraction_prompt_includes_existing_domains`** —
   Call `build_extraction_prompt()` with `existing_entries` containing 3
   entries with domains `["python", "testing", "auth"]`. Verify the returned
   prompt string contains "Use one of these existing domain tags" and lists
   the domain names.

2. **`test_extraction_prompt_caps_domains_at_20`** —
   Pass entries with 30 unique domains. Verify only 20 appear in the prompt.

3. **`test_extraction_prompt_no_domains_without_existing`** —
   Call with `existing_entries=None`. Verify no domain hint appears.

### Track 3 tests — `tests/unit/engine/test_scoring_math_ess.py`

4. **`test_rescale_preserving_mean_under_cap`** —
   Call `rescale_preserving_mean(10.0, 5.0)`. Verify returned unchanged
   (ESS=15 < 150).

5. **`test_rescale_preserving_mean_over_cap`** —
   Call `rescale_preserving_mean(100.0, 80.0)`. Verify ESS is capped at
   150 and mean ratio is preserved: `100/180 ≈ new_alpha/(new_alpha+new_beta)`.

6. **`test_rescale_preserving_mean_exact_cap`** —
   Call `rescale_preserving_mean(75.0, 75.0)`. Verify returned unchanged
   (ESS=150, exactly at cap).

7. **`test_rank_credit_top_entry_gets_more`** —
   Integration test: simulate a colony outcome with 3 accessed entries at
   ranks 0, 1, 2. Verify rank-0 entry gets `1.0x` delta, rank-1 gets
   `0.7x`, rank-2 gets `0.49x`.

8. **`test_ess_cap_after_outcome_update`** —
   Set an entry's alpha+beta to 145. Apply an outcome update. Verify the
   result is capped at 150.

9. **`test_auto_promotion_works_with_ess_cap`** —
   Verify that auto-promotion (candidate → verified when alpha >= threshold)
   still triggers correctly after ESS rescaling.

---

## Acceptance Gates

All must pass before declaring done:

**Track 2:**
- [ ] Extraction prompt shows "Use one of these existing domain tags" when
  existing entries have domains
- [ ] Domain hint caps at 20 domains
- [ ] No hint appears when `existing_entries` is None or empty
- [ ] No regression in extraction quality (domains still free-form if no
  existing entries match)

**Track 3:**
- [ ] `rescale_preserving_mean()` exists in `engine/scoring_math.py`
- [ ] ESS cap at 150 preserves posterior mean
- [ ] Top-ranked entries get stronger confidence reinforcement (0.7^rank)
- [ ] Alpha+beta never exceeds 150 after outcome update
- [ ] Mastery restoration still works correctly with capped entries
- [ ] Auto-promotion still triggers when alpha crosses threshold
- [ ] Co-occurrence reinforcement unchanged (line ~1618)
- [ ] No new event types (stays at 69)
- [ ] No changes to `core/types.py`

---

## Validation

Run the full CI suite before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass clean. Target: 3654 + 9 = 3663+ tests (3 Track 2 + 6 Track 3).

The `lint_imports.py` check is critical for Track 3: the `rescale_preserving_mean`
function is in Engine, imported by Surface. This is the correct direction
(Surface → Engine). If you accidentally create an Engine → Surface import,
`lint_imports.py` will catch it.

---

## Overlap Reread Rules

After completing your work, reread:

- `src/formicos/surface/memory_extractor.py` lines 88–130 (your Track 2 changes)
- `src/formicos/surface/colony_manager.py` lines 1476–1620 (your Track 3 changes)
- `src/formicos/engine/scoring_math.py` (your new function)

Verify:
- Domain hint doesn't break existing prompt structure
- Rank credit doesn't change co-occurrence reinforcement logic
- ESS cap doesn't prevent mastery restoration or auto-promotion
- `peak_alpha` tracking in projections still records the true peak

---

## Track Summary Template

When done, report:

```
Track 2: Domain Normalization
- Files modified: [list]
- Tests added: [count]
- existing_entries populated at call site: [yes/no/partially — explain]

Track 3: Rank Credit + ESS Cap
- Files modified: [list]
- Tests added: [count]
- Access record structure: [describe what you found]
- Mastery restoration verified: [yes/no]
- Auto-promotion verified: [yes/no]
- Additional bugs found/fixed (audit allowance): [list or none]
```
