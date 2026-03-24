# Audit Demo Scaffold

A runbook for demonstrating FormicOS's causal auditability. This demo
shows that an operator can trace any knowledge-driven decision back to
its origin — which entry was used, where it came from, why it was
retrieved, and what the operator did about it.

This is the strongest differentiator. Most agent systems are opaque.
FormicOS is event-sourced, replay-safe, and operator-visible.

---

## Prerequisites

- [ ] FormicOS stack running with at least one workspace containing
      knowledge entries
- [ ] At least one colony that accessed knowledge during execution
- [ ] Ideally: the demo workspace (`POST /api/v1/workspaces/create-demo`)
      which includes seeded entries and a deliberate contradiction

---

## Demo Structure (target: 8-12 minutes)

### Part 1: Pick an Entry (2 min)

Start from a knowledge entry and trace its full lifecycle.

1. Open the Knowledge browser
2. Pick an entry — ideally one with:
   - confidence that has evolved (alpha > 1 or beta > 1)
   - at least one access (entries_accessed > 0)
   - a decay class other than permanent

3. Show the entry's metadata:
   - content and domains
   - confidence: `Beta(alpha, beta)` — explain what this means
   - decay class: ephemeral / stable / permanent
   - sub_type: technique / pattern / decision / etc.
   - status: candidate / validated / invalidated

### Part 2: Where Did It Come From? (2-3 min)

Trace the entry's origin.

**If colony-extracted:**
- Which colony produced it?
- Which task was the colony working on?
- Was it extracted via LLM extraction or transcript harvest?
- Did it pass the 5-axis security scan?

**If forager-sourced:**
- Source URL
- Fetch timestamp
- Source credibility tier
- Extraction quality score
- Which gap triggered the forage cycle?

**If seeded (demo workspace):**
- Show that demo entries have known provenance
- Point out the deliberate contradiction (if using demo workspace)

### Part 3: Who Used It? (2-3 min)

Trace the entry's usage.

1. Show which colonies accessed this entry during retrieval
2. Show the retrieval scoring breakdown _(when explainable retrieval
   surfaces are available)_:
   - semantic similarity contribution
   - Thompson Sampling contribution
   - freshness contribution
   - status contribution
   - thread bonus (if same-thread)
   - co-occurrence contribution
3. Show whether the colony that used it succeeded or failed
4. Show how confidence evolved after that colony completed:
   - successful colony -> alpha increase
   - failed colony -> beta increase

### Part 4: What Did the Operator Do? (2 min)

Show operator co-authorship over knowledge.

1. Pin or unpin the entry — show this is a local overlay, not a
   confidence mutation
2. Annotate the entry — show the annotation is replayable
3. If the demo workspace has a contradiction:
   - Show the two contradicting entries
   - Show that the system detected the contradiction (proactive briefing)
   - Show the operator resolving it via invalidate or mute
4. Show that these overlays survive replay (restart the stack and verify)

### Part 5: The Competing Hypothesis Story (2 min)

_(Requires competing hypothesis surfacing from Wave 45 Team 2.)_

1. Show two entries tagged as `competing_with` each other
2. Show that retrieval annotates the tension: "this entry competes with
   entry X at confidence Y"
3. Show that the operator can resolve by:
   - validating one and invalidating the other
   - keeping both (the system tolerates uncertainty)
   - pinning one to force retrieval preference

---

## Capture Checklist

Record during the demo:

- [ ] Which entry was traced
- [ ] Whether the entry was colony-extracted or forager-sourced
- [ ] Whether the retrieval breakdown was available
- [ ] Whether operator overlays survived replay
- [ ] Whether competing hypotheses were visible
- [ ] Audience questions about auditability gaps

---

## Key Operator Surfaces Used

| Surface | What It Shows | Status |
|---------|---------------|--------|
| Knowledge browser | Entry list with metadata | Exists |
| Entry detail view | Full entry with confidence, domains, status | Exists |
| Proactive briefing | Contradiction detection, coverage gaps | Exists |
| Retrieval score breakdown | Per-signal scoring explanation | Exists (standard/full tier) |
| Web-source badge | Forager provenance on entries | Exists |
| Forager cycle history | What was searched/fetched/admitted | Exists (API) |
| Competing hypothesis tags | `competing_with` annotation | Exists (projection) |
| Operator overlays | Pin/mute/invalidate/annotate | Exists |

---

## What NOT to Do

- Do not trace an entry you seeded yourself and claim "the system found
  this" — distinguish seeded from extracted
- Do not show retrieval scoring without explaining that weights are
  configurable per workspace
- `knowledge_used` and `knowledge_attribution` are populated from
  projection truth — use them for real traceability claims
- Do not demo features that exist only in backend projections but have
  no operator surface — say "this data exists but is not yet exposed in
  the UI"
