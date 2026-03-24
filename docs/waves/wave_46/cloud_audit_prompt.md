## Role

You are auditing the Wave 46 packet before coder dispatch.

This is a **product-first proof wave**, not a benchmark-first build wave.
Your job is to pressure-test whether the packet stays loyal to that identity.

## Read first

1. `docs/waves/wave_46/wave_46_plan.md`
2. `docs/waves/wave_46/acceptance_gates.md`
3. `docs/waves/wave_46/coder_prompt_team_1.md`
4. `docs/waves/wave_46/coder_prompt_team_2.md`
5. `docs/waves/wave_46/coder_prompt_team_3.md`
6. `AGENTS.md`
7. `CLAUDE.md`

Then ground your review against the live repo.

## Context you should assume

Post-Wave-45.5 repo truth includes:

- proactive foraging live through maintenance dispatch
- competing-hypothesis surfacing live through replay-derived projection state
- source-credibility-aware admission live for forager entries
- 62 events in the closed union
- Forager service and projection state exist, but operator surface is still thin
- eval harness exists, but still has integrity gaps

## Core audit question

For every major item in the packet, ask:

**If the benchmark disappeared tomorrow, would we still want this change in FormicOS?**

If the answer is no, call it out.

## What to audit

### 1. Check repo-grounding

Verify that the packet’s claimed gaps are real in the current code:

- forager operator surface
- web-source visibility in the UI
- OTel wiring
- search/fetch policy cohesion
- eval harness workspace reuse / empty `knowledge_used` / thin conditions
- task suite size

### 2. Check for benchmark drift

Look for any place where the packet:

- turns the product into a benchmark runner
- implies benchmark-specific product logic
- encourages one-off task/suite hacks
- overprioritizes score over operator usefulness

### 3. Check team boundaries

Verify the three tracks are clean:

- Team 1: forager operator surface + product cohesion
- Team 2: eval harness + measurement integrity
- Team 3: analysis/demo/publication scaffolding

Call out file overlap risks if they are real.

### 4. Check “no unearned features” discipline

The packet allows bounded product improvements. Audit whether any item crosses
the line into:

- new subsystem creation
- event growth
- adapter sprawl
- architecture rewrite

### 5. Check acceptance gates

Make sure the gates protect:

- operator-visible Forager truth
- measurement integrity
- no benchmark-only product path
- no overclaiming of results before data exists

### 6. Check coder prompts

Make sure the prompts:

- point coders at real seams
- include the anti-drift rule explicitly
- do not accidentally authorize benchmark-only work
- do not silently expand scope

## Deliverable format

Report findings by severity:

- Blocker
- Medium
- Low
- Informational

Then give a verdict:

- dispatch-ready
- dispatch-ready with prompt tweaks
- not ready

## Special attention

1. If the packet is too strict about “no features,” say so.
   Wave 46 intentionally allows small product improvements that generalize.
2. If the packet still underweights operator-visible Forager surfaces relative
   to pure measurement work, say so.
3. If the packet lets Team 2 smuggle benchmark-specific logic into product
   code, say so.
4. If Team 3’s role is too aspirational before data exists, say so.
