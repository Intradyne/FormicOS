Audit the live repo against the corrected Wave 51 packet before coder dispatch.

This is not a redesign brainstorm. It is a repo-truth check on whether Wave 51
is correctly scoped as a subtractive polish / capability-truth wave and whether
the remaining items are still the right ones after stale findings were removed.

## Read First

1. `docs/waves/wave_51/wave_51_plan.md`
2. `docs/waves/wave_51/acceptance_gates.md`
3. `docs/waves/wave_51/ui_audit_findings.md`
4. `docs/waves/wave_51/ui_seam_map.md`
5. `docs/waves/wave_51/backend_audit_findings.md`
6. `docs/waves/wave_51/backend_seam_map.md`
7. `docs/waves/wave_50/status_after_plan.md`
8. `AGENTS.md`
9. `CLAUDE.md`

Then verify the relevant code seams directly.

## Core Questions

1. Is Wave 51 now correctly limited to confirmed truth debt rather than stale
   audit findings?
2. Are the replay-safety seams (`escalate_colony`, Queen notes,
   `dismiss-autonomy`) the right top priority for this wave?
3. Does the plan keep global promotion and learned-template enrichment in the
   already-landed bucket rather than accidentally reopening Wave 50?
4. Is the Queen-note fix direction safe, or does it risk leaking internal
   thread-note context into visible operator chat?
5. Are the degraded-state fixes truly subtractive/polish work rather than
   stealth backend scope creep?
6. Is the team split still clean after moving scope away from A3/A4/B4?
7. Does the packet preserve product identity: trust alignment, not a new
   architecture wave?

## Verify These Specific Claims

### Claim A: Global promotion is already landed and should stay out of Wave 51

Check:

- `src/formicos/core/events.py`
- `src/formicos/surface/routes/knowledge_api.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/memory_store.py`
- `src/formicos/surface/knowledge_catalog.py`
- `frontend/src/state/store.ts`

Confirm that:

- `MemoryEntryScopeChanged` supports workspace/global promotion semantics
- promotion route accepts `target_scope="global"`
- projections handle `scope="global"`
- retrieval includes global entries
- Wave 51 should not hide or demote that UI

### Claim B: Learned-template enrichment is already landed and should stay out of Wave 51

Check:

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/template_manager.py`
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/queen_tools.py`

Confirm that:

- learned-template additive fields exist
- learned template projections carry success/failure and provenance metadata
- template loading merges operator-authored and learned templates
- Wave 51 should not hide or relabel learned-template UI as "future"

### Claim C: `escalate_colony` is still not replay-safe

Check:

- `src/formicos/surface/queen_tools.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`

Confirm whether:

- escalation still mutates in-memory projection state directly
- no replay-safe event currently captures it
- the packet's top priority is justified

### Claim D: Queen notes still lack a correct replay-safe persistence seam

Check:

- `src/formicos/surface/commands.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/projections.py`

Confirm whether:

- WS-saved notes remain in-memory only
- tool-saved notes remain YAML-backed only
- notes are part of Queen working context rather than ordinary visible chat

Also answer explicitly:

- Is a dedicated hidden note event the right direction?
- Would using visible `QueenMessage` rows for persistence be a product/seam mistake?

### Claim E: `dismiss-autonomy` is a real durability-classification seam

Check:

- `src/formicos/surface/routes/api.py`
- any overlay/projection code it touches

Confirm whether:

- dismissals remain memory-only
- the right fix is "event it or label it ephemeral," not "pretend it is durable"

### Claim F: Visible degraded-state work is still real

Check:

- `frontend/src/components/config-memory.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/proactive-briefing.ts`

Confirm whether:

- config-memory still swallows partial fetch failures silently
- Queen overview still hides unavailable sections
- model/protocol freshness is still snapshot-heavy
- strategy pills still look interactive
- proactive briefing still shows domain trust state without inline controls

### Claim G: `fleet-view.ts` and vocabulary cleanup are still worth doing

Check:

- `frontend/src/components/fleet-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts`
- relevant operator-facing components

Confirm whether:

- `fleet-view.ts` is still dead
- operator-facing "Skill Bank" language is still leaking
- "Config Memory" still reads as historically accurate but operator-ambiguous

### Claim H: `docs/REPLAY_SAFETY.md` really belongs in the wave

Check the packet and the audits together and answer:

- Is replay-safety documentation a real deliverable, not just documentation padding?
- Does it materially improve operator/contributor truth?
- Is it important enough to sit near the top of the priority list?

## Team-Split Audit

Check whether the current ownership is clean:

- Team 1: replay safety + backend truth
- Team 2: surface truth + visible degradation
- Team 3: docs + vocabulary + final truth

Call out hidden overlap risk, especially in:

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `docs/REPLAY_SAFETY.md`
- `frontend/src/state/store.ts`

## Product-Identity Audit

Answer explicitly:

1. Does each Must item help arbitrary operators rather than just audit purity?
2. Does the packet stay subtractive?
3. Does the packet avoid reopening already-landed Wave 50 substrate?
4. Does it avoid turning polish into a stealth architecture wave?
5. Is anything still misclassified and better filed as follow-up debt?

## Output Format

Return:

1. Findings first, ordered by severity, with file references
2. Repo-truth confirmation of the corrected Wave 51 scope
3. Any corrections needed before coder dispatch
4. A team-split / overlap-risk check
5. A product-identity / scope-purity check
6. A short verdict: audit-ready or not, and why

## Important Guardrails

- Do not re-argue for already-landed A3/A4 work unless current code disproves
  the corrected packet
- Do not recommend broad runtime work like streaming fallback unless you think
  it is necessary enough to break Wave 51's subtractive charter
- Evaluate this wave by operator trust, replay-safe truth, and seam honesty,
  not by whether it adds more backend depth
