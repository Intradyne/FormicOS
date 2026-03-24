# Wave 34 Team 3 — Entry Sub-types + Frontend + Demos

## Role

You are adding knowledge entry sub-types, confidence visualization, federation dashboard, proactive briefing display, and end-to-end demo scenarios. All your work runs in parallel with Teams 1 and 2 — no dependencies, no gating.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Team 2 also modifies `surface/mcp_server.py` (briefing resource + knowledge_feedback tool). You modify the existing `formicos://knowledge` resource handler to add sub_type filtering. **Do not add new resources or tools to mcp_server.py** — Team 2 owns those.
- Your frontend component `proactive-briefing.ts` displays data from Team 2's `ProactiveBriefing` model. Use the schema from the Team 2 prompt (or read `surface/proactive_intelligence.py` once Team 2 lands). If Team 2 hasn't landed yet, build against the documented schema — the Pydantic model is stable.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `core/types.py` | MODIFY | EntrySubType StrEnum, sub_type field on MemoryEntry |
| `surface/memory_extractor.py` | MODIFY | Sub-type in extraction + harvest prompts |
| `surface/mcp_server.py` | MODIFY | sub_type filter on `formicos://knowledge` resource **ONLY** |
| `surface/routes/knowledge_api.py` | MODIFY | sub_type filter parameter |
| `frontend/src/components/knowledge-browser.ts` | MODIFY | Confidence visualization |
| `frontend/src/components/federation-dashboard.ts` | CREATE | Peer trust, sync, conflicts |
| `frontend/src/components/proactive-briefing.ts` | CREATE | Insight display with severity badges |
| `docs/demos/demo-email-validator.md` | CREATE | End-to-end demo scenario 1 |
| `docs/demos/demo-federation.md` | CREATE | End-to-end demo scenario 2 |
| `docs/demos/demo-knowledge-lifecycle.md` | CREATE | End-to-end demo scenario 3 |
| `tests/unit/surface/test_entry_subtypes.py` | CREATE | Sub-type mapping tests |

## DO NOT TOUCH

- `surface/knowledge_catalog.py` — Team 1 owns (tiered retrieval, co-occurrence scoring)
- `surface/knowledge_constants.py` — Team 1 owns (COMPOSITE_WEIGHTS)
- `engine/runner.py` — Team 1 owns (budget assembly), Team 2 owns (knowledge_feedback dispatch)
- `config/caste_recipes.yaml` — Team 2 owns (Queen prompt, tool arrays)
- `surface/proactive_intelligence.py` — Team 2 owns (insight generation)
- `surface/queen_runtime.py` — Team 2 owns (insight injection)
- `surface/routes/api.py` — Team 2 owns (briefing endpoint)
- All integration/stress test files — Validation track owns
- `CLAUDE.md`, `KNOWLEDGE_LIFECYCLE.md`, `AGENTS.md` — Validation track owns
- `pyproject.toml` — Validation track owns

## Overlap rules

- `surface/mcp_server.py`: **Team 2 also modifies this file** (adding briefing resource after line 467 and knowledge_feedback tool). You own: modifications to the existing `formicos://knowledge` resource handler (adding `sub_type` filter parameter). Do not add new resource handlers or tool registrations — Team 2 owns those.

---

## B3. Knowledge entry sub-types

### Where

`core/types.py` — add `EntrySubType` StrEnum near existing enums (line 315-336 area). Add `sub_type` field to `MemoryEntry` (line 339+).

### Implementation

```python
class EntrySubType(StrEnum):
    # Under "skill"
    technique = "technique"
    pattern = "pattern"
    anti_pattern = "anti_pattern"
    # Under "experience"
    decision = "decision"
    convention = "convention"
    learning = "learning"
    bug = "bug"
```

Add to MemoryEntry:
```python
sub_type: EntrySubType | None = Field(default=None, description="Granular sub-type within skill/experience.")
```

**In memory_extractor.py** — update `build_extraction_prompt()` (line 30) and `build_harvest_prompt()` (line 172) to classify sub_type. The harvest already classifies as bug/decision/convention/learning (HARVEST_TYPES at line 164) — map to EntrySubType.

**Filter support:** Add `sub_type` parameter to `routes/knowledge_api.py` and the MCP `formicos://knowledge` resource filter.

### Tests

- Extraction prompt includes sub_type classification instruction
- Harvest types map correctly: bug→bug, decision→decision, convention→convention, learning→learning
- Knowledge API filters by sub_type
- MCP knowledge resource filters by sub_type
- Default sub_type is None (existing entries unaffected)

---

## B4. Confidence visualization

### Where

`frontend/src/components/knowledge-browser.ts` — enhance existing knowledge entry display.

### Implementation

**Default view:** Gradient-opacity confidence bar. Color-coded tier badge:
- Gray: STALE
- Red: EXPLORATORY
- Yellow: LOW/MODERATE
- Green: HIGH

Natural-language summary: "High confidence (72%) — 47 observations, stable decay class."

**Hover view:** Numeric mean ± credible interval, observation count, decay class, federation source indicator, co-occurrence cluster membership, prediction error count.

**Power user panel** (expandable): Raw alpha/beta, merged_from provenance list.

Use the same `_confidence_tier()` classification logic from engine/runner.py (lines 388-423) — reimplement in TypeScript for the frontend.

---

## B5. Federation dashboard

### Where

Create `frontend/src/components/federation-dashboard.ts`.

### Implementation

- Peer trust table: instance_id, trust score, success/failure counts, last sync
- Sync status: last_sync_clock per peer, events pending push/pull
- Conflict log: recent ConflictResult entries with resolution method
- Knowledge flow: entries sent/received per peer, domains exchanged

All data from projections — PeerConnection state, conflict resolution history, federation event counts.

---

## B6. End-to-end demo scenarios

### What

Three complete walkthroughs documented as markdown + integration tests.

Create in `docs/demos/`:

**demo-email-validator.md:** Operator says "build me an email validator with tests." System decomposes via Queen, executes colony, extracts knowledge, tiered retrieval in future colonies uses the extracted knowledge, proactive briefing shows confidence growing.

**demo-federation.md:** Two instances. Instance A builds testing knowledge. Replicates to B. B uses in colony. Validation feedback. Trust evolves. Proactive insight fires when trust changes.

**demo-knowledge-lifecycle.md:** Entry creation with sub-type classification, decay class assignment, confidence evolution through colony outcomes, merge via dedup, archival burst, recovery on re-access, prediction errors, stale sweep. Proactive briefing surfaces each transition.

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

For frontend changes: verify Lit components compile and render correctly.
