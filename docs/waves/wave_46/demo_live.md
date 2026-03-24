# Live Demo Scaffold

A runbook for demonstrating FormicOS to a live audience. The demo uses a
real measured task as the backbone, not a staged script.

---

## Prerequisites

- [ ] FormicOS stack running (`docker compose up -d`)
- [ ] Health checks pass: backend `:8080/health`, sidecar `:8008/health`,
      Qdrant `:6333/collections`
- [ ] At least one successful eval run exists (for the recorded portion)
- [ ] Model API key configured (cloud) or local GGUF models loaded

---

## Demo Structure (target: 10-15 minutes)

### Part 1: The System (2 min)

Show the operator what FormicOS is before showing what it does.

1. Open `http://localhost:8080`
2. Show the Queen landing page
3. Point out: this is a local-first system — the SQLite file is the source
   of truth, events replay into projections on startup

Key message: "This is an editable shared brain with operator-visible traces,
not an autonomous agent swarm."

### Part 2: Recorded Run Walkthrough (5 min)

Use a real eval run result as the narrative backbone.

1. Show the compounding curve from a completed run
   - Source: `data/eval/sequential/{suite_id}/run_{timestamp}.json`
   - Visualize with `python -m formicos.eval.compounding_curve --suite {id}`
2. Walk through 2-3 tasks in sequence:
   - Task 1: baseline (no prior knowledge)
   - Task 3-4: show knowledge accumulation (entries_extracted > 0,
     entries_accessed > 0 in later tasks)
   - If a task failed: show it honestly. Explain why.
3. Show the locked conditions: model mix, budget, escalation policy
4. Point out what is NOT magic: the task order matters, the model matters,
   the budget matters

### Part 3: Live Challenge (3-5 min)

Run a fresh task live to show the system is real, not pre-recorded.

1. Create a new workspace or use the demo workspace
   (`POST /api/v1/workspaces/create-demo`)
2. Give the Queen a task that is:
   - simple enough to complete in < 2 minutes
   - related to a domain where seeded knowledge exists
3. Watch the colony execute in real time:
   - rounds progressing
   - knowledge retrieval happening (or not)
   - cost accumulating
4. Show the result. If it fails, narrate the failure honestly.

### Part 4: What Makes This Different (2 min)

- Every action is an event. Show the event log.
- Knowledge has Bayesian confidence. Show an entry with alpha/beta.
- The operator can pin, mute, invalidate, annotate. Show one.
- The system detects its own problems. Show the proactive briefing.

---

## Capture Checklist

Record these during the demo for post-demo reporting:

- [ ] Which suite and run was used for the walkthrough
- [ ] Which task was run live
- [ ] Whether the live task succeeded or failed
- [ ] Any unexpected behavior observed
- [ ] Audience questions that revealed product gaps

---

## Failure Contingencies

| Failure | Response |
|---------|----------|
| Stack won't start | Show the recorded run only. Be transparent. |
| Live task times out | Show partial progress. Explain budget/round limits. |
| Live task fails | Narrate the failure. This is honest, not embarrassing. |
| Knowledge retrieval returns nothing | Explain: the knowledge catalog may be empty if this is a fresh workspace. |
| Model API errors | Switch to local model if available. Otherwise, recorded-only demo. |

---

## What NOT to Do

- Do not use a pre-scripted colony with cached outputs
- Do not hide failures
- Do not claim "this always works" — show locked conditions instead
- Do not frame the benchmark as the product. The product is the shared brain.
- Do not demo features that only exist in code but have no operator surface
