# Wave 33.5 Team 3 — Wave 33 Validation + Documentation Sync

## Role

You are the integration validator. Run the full Wave 33 smoke test sequence (19 items from the plan), fix anything broken, and sync all documentation to the post-Wave-33 codebase. This is the gate before Wave 34.

## File ownership

You have permission to touch ANY file to fix validation issues. But you must document every fix. For documentation sync, you own:

| File | Status | Changes |
|------|--------|---------|
| `CLAUDE.md` | MODIFY | Update for Wave 33 additions |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | Cover all Wave 33 knowledge pipeline additions |
| `AGENTS.md` | MODIFY | Sync tool lists, add federation info |

For validation fixes, you may touch any source file, but:
- Document what you changed and why
- Prefer minimal fixes (don't refactor)
- Run full CI after each fix

## DO NOT TOUCH (unless fixing a validation failure)

- `config/caste_recipes.yaml` — Team 1 owns
- `engine/runner.py` — Team 2 owns (search enrichment)
- `surface/runtime.py` — Team 2 owns (transcript enrichment)

---

## Task 3a: Wave 33 smoke test validation

Run each of the 19 items from the Wave 33 plan's Smoke Test section. For each item, report: PASS, FAIL (with details), or FIXED (with what you changed).

### Smoke test items

**1. Colony lifecycle regression check**
Create workspace, thread, 3 workflow steps. Run colonies. Verify step continuation works. This is a Wave 31 regression check.

**2. Transcript harvest**
Colony with tool-call failure followed by fix → transcript harvest extracts bug-type entry. Structured extraction does NOT capture it (only sees compressed summary).

**3. Inline dedup**
Two colonies on related tasks complete within seconds → inline dedup prevents near-duplicate entries.

**4. Prediction errors**
Search returns semantically-weak top result → entry's prediction_error_count incremented.

**5. Permanent decay class**
Entry with decay_class="permanent" → no confidence decay after 30 days.

**6. Gamma cap**
Entry with decay_class="ephemeral" not observed for 180 days → alpha capped at ~18 (not collapsed to ~5).

**7. Credential detection**
Knowledge entry with embedded API key → scan_status="high", status="rejected".

**8. Credential redaction**
A2A `/tasks/{id}/result` → credentials in tool outputs redacted as `[REDACTED:type]`.

**9. StructuredError**
MCP tool with bad workspace_id → response includes WORKSPACE_NOT_FOUND error_code, recovery_hint, suggested_action.

**10. MCP resources**
`formicos://knowledge` MCP resource → returns entries. Subscribe → notification fires after colony extracts knowledge.

**11. Agent Card**
Agent Card at `/.well-known/agent.json` → includes knowledge_domains with counts + federation section.

**12. Co-occurrence**
Successful colony → co-occurrence weights reinforced for accessed entry pairs. Maintenance loop → weights decayed.

**13. CRDT merge**
Two ObservationCRDTs with different observation counts → merge → query_alpha() correct at given timestamp. Provide the exact computation:
```
Instance A: 5 successes, last_obs at t-10 days
Instance B: 3 successes, last_obs at t-2 days
gamma=0.98, prior_alpha=5.0
Expected alpha = 5.0 + (0.98^10 * 5) + (0.98^2 * 3)
             = 5.0 + (0.8171 * 5) + (0.9604 * 3)
             = 5.0 + 4.0855 + 2.8812
             = 11.967
```

**14. PeerTrust scoring**
PeerTrust(11, 1).score → ~0.79 (10th percentile, NOT 0.917 mean).

**15. Conflict resolution**
Contradictory entries → Pareto dominance resolves obvious case. Adaptive threshold handles close case.

**16. Federation round-trip**
Federation round-trip (mock transport): A creates entry → replicates to B → B uses in colony → feedback to A → A's trust updated.

**17. Dedup merge event**
Dedup auto-merge (>= 0.98 similarity) → emits MemoryEntryMerged (not MemoryEntryStatusChanged) with unioned domains and merged_from.

**18. Full replay**
Full replay of all event types including new CRDT events → projections identical.

**19. CI clean**
`pytest` all pass. `pyright src/` 0 errors. `lint_imports.py` 0 violations.

### How to run smoke tests

Items 1-8, 12-13, 17-18 can be verified with unit tests (check existing tests or write minimal verification scripts).
Items 9-11 require instantiating the MCP server or checking the route handlers.
Items 14-16 can be verified with direct function calls.
Item 19: run full CI.

For each item, write a brief test or verification script if one doesn't already exist. Collect results in a summary table.

---

## Task 3b: Documentation sync

### CLAUDE.md updates

The current CLAUDE.md references 48 events. Update to reflect the post-Wave-33 state. Key changes:

1. **Event union:** Change "48" to "53" in hard constraint #5. Update the wording per ADR-042 D3:
   > Event types are a CLOSED union — adding types requires an ADR with operator approval.

2. **Architecture section:** Add mentions of:
   - Credential scanning (5th security axis, detect-secrets)
   - StructuredError across all 5 surfaces (KNOWN_ERRORS registry)
   - MCP resources and prompts (with ResourcesAsTools/PromptsAsTools transforms)
   - Federation architecture (Computational CRDTs, trust discounting, conflict resolution)
   - Decay classes (ephemeral/stable/permanent) with gamma rates
   - Co-occurrence data collection (scoring deferred to Wave 34)
   - Transcript harvest at hook position 4.5

3. **Key paths table:** Add:
   - `surface/credential_scan.py` — Credential scanning + redaction
   - `surface/trust.py` — Bayesian peer trust scoring
   - `surface/conflict_resolution.py` — Pareto + adaptive threshold conflict resolution
   - `surface/federation.py` — Federation protocol (push/pull replication)
   - `core/crdt.py` — CRDT primitives + ObservationCRDT
   - `surface/transcript_view.py` — Canonical colony transcript schema

4. **Knowledge system section:** Update composite scoring description to note co-occurrence data is being collected (Wave 33) but not yet in the scoring formula (Wave 34).

5. **Common patterns:** Add "Adding a maintenance handler" pattern:
   ```
   1. Create make_*_handler(runtime) factory in maintenance.py
   2. Register in app.py service_router.register_handler() block
   3. Add to maintenance.py __all__
   ```

### KNOWLEDGE_LIFECYCLE.md updates

This is the operator runbook. Add sections for every Wave 33 knowledge pipeline addition:

- **Transcript harvest:** What it extracts (bug root causes, conventions, tool configs), hook position 4.5, dedup at 0.82 threshold, replay safety via `:harvest` suffix
- **Inline dedup:** Cosine > 0.92 check before emission, reinforces existing entry confidence
- **Credential scanning:** Dual-config (prose vs code), 5th security axis, +2.0 score for credential findings, retroactive sweep handler
- **Prediction error counters:** Semantic < 0.38 threshold, projection-only (lossy on replay), feeds stale_sweep at count >= 5 + access < 3
- **Co-occurrence:** Result-result (1.1x on colony success) + query-result (1.05x) reinforcement, gamma=0.995 decay, prune < 0.1, scoring deferred to Wave 34
- **Federation:** ObservationCRDT model, trust discounting (10th percentile), conflict resolution (Pareto + adaptive threshold), push/pull replication
- **Decay classes:** ephemeral (0.98, ~34d), stable (0.995, ~139d), permanent (1.0), MAX_ELAPSED_DAYS=180
- **MemoryEntryMerged:** Replaces rejection for dedup auto-merges, content strategy (keep_longer), domain union, merged_from provenance

### AGENTS.md updates

- Verify tool lists per caste match `config/caste_recipes.yaml` `tools:` arrays
- Add any new tool descriptions that reflect Wave 33 capabilities
- Add federation section for operators

---

## Validation

After all fixes and doc updates:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Produce a final summary:
```
Wave 33 Smoke Test Results:
  Pass: X/19
  Fixed: Y/19 (list what was fixed)
  Known issues: Z (list any deferred items)

Documentation:
  CLAUDE.md: Updated (list sections changed)
  KNOWLEDGE_LIFECYCLE.md: Updated (list sections added)
  AGENTS.md: Updated (list changes)

Final CI:
  ruff: pass/fail
  pyright: X errors
  lint_imports: X violations
  pytest: X passed, Y failed
```
