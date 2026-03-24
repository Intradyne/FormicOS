# Development Workflow

This document is the canonical reference for how FormicOS work should move
from planning through acceptance. It is meant to reduce drift between
`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, and active wave packets.

It does not replace wave plans. It tells contributors and orchestrators how to
execute them cleanly.

---

## Source of Authority

Use repo guidance in this order:

1. active wave docs and dispatch prompts for wave-specific ownership and scope
2. `CLAUDE.md` for evergreen repo rules and coordination discipline
3. root `AGENTS.md` for capability and coordination defaults when it still
   matches the active wave
4. `CONTRIBUTING.md` for external PR flow, local setup, and CI expectations

If two docs disagree, say which one you are following instead of silently
assuming the answer.

Future-wave docs that are explicitly marked **provisional** are directional
only. They help shape the next packet, but they do not override the active
wave and do not count as dispatch-ready by themselves.

---

## Two Working Modes

### 1. Shared-workspace wave execution

This is the default mode for orchestrated FormicOS wave work:

- the operator or orchestrator defines the active wave packet
- work is split into bounded parallel tracks
- acceptance happens by seam first, smoke second
- polish follows substrate acceptance

This mode is optimized for:

- parallel AI coding tracks
- fast integration in one workspace
- replay / projection / protocol truth checks

### 2. External branch / PR contribution

This is the default mode for outside contributors:

- fork or branch from the current trunk
- keep the change focused
- run CI locally
- submit a PR with a clear change description

This mode is optimized for:

- normal GitHub contribution flow
- human review and merge
- narrower changes that do not depend on live multi-track dispatch

These modes overlap, but they are not identical. Do not force the branch/PR
mental model onto shared-workspace wave execution, and do not assume external
contributors are operating with a live wave packet in front of them.

---

## Standard Delivery Loop

Unless the active wave says otherwise, follow this sequence.

### 0. Establish the active coordination source

- confirm the active wave packet
- confirm whether `AGENTS.md` still matches it
- confirm which seams are frozen (`docs/contracts/`, event union, ADR-backed
  decisions)

### 0.5 Decide packet maturity before writing too much

Use explicit packet statuses:

- **provisional plan** -- direction only; useful while the current wave is
  still in flight
- **packet written** -- plan, gates, coder prompts, and audit prompt exist
- **dispatch-ready** -- packet has been audited and patched
- **in progress** -- coder tracks are active
- **accepted** -- seam truth and runtime truth have been checked and the wave
  is accepted as landed

Best practice:

- while the current wave is still in flight, future-wave planning should
  usually stop at a provisional plan unless the operator explicitly wants
  more
- write acceptance gates and coder prompts against real leftovers, not
  imagined debt carried forward from an unfinished wave
- before freezing a packet, sort notable findings into explicit buckets:
  - confirmed current drivers
  - re-verify before packet freeze
  - already landed, do not reschedule
  - reference only / future scope

This prevents loud early audit findings from reopening landed substrate or
re-queuing hardening that already shipped.

### 1. Ground the plan in repo truth

- read the relevant wave docs, ADRs, and contract docs
- inspect the current source paths that actually carry truth
- classify problems before proposing fixes:
  - substrate truth
  - surface truth
  - runtime / deployment truth
- use research to validate or tighten a wave, not to broaden it by default

Do not assume the running UI, Docker image, or persisted state matches the
source tree you are reading.

### 2. Bound the work into tracks

Each track should have:

- a concrete mission
- explicit owned files
- a do-not-touch list
- validation commands
- overlap reread rules if needed

Good tracks leave behind usable progress. Avoid tracks that only lay plumbing
unless the wave explicitly requires that.

For true parallel waves, also prefer:

- disjoint write sets whenever possible
- one clear owner for any shared canonical doc
- a docs-only track that can start immediately but finish in a second truth
  pass after code tracks land, when needed

### 3. Write the packet before dispatch

A normal wave packet should include:

- plan
- acceptance gates
- bounded coder prompts
- an audit prompt

If the wave is not mature enough for those artifacts, keep it provisional
instead of forcing fake precision.

### 4. Audit the packet before dispatch

Use a seam-focused audit before coder dispatch.

The audit should:

- verify the packet against the live repo
- flag only real blockers, misleading assumptions, or scope mistakes
- prefer the smallest set of prompt/gate fixes needed before dispatch

Best practice:

- patch the smallest set of packet docs that close the audit finding
- avoid destabilizing the whole wave because of one prompt-level correction
- let the live repo referee research claims
- if a finding looks dramatic, re-verify it against current code before making
  it packet-driving truth
- explicitly remove stale findings and already-landed work from active scope
  instead of leaving them as implicit caveats

### 5. Dispatch with explicit contracts

Good dispatch prompts state:

- what the team owns
- what it must not touch
- the hard constraints for the wave
- the specific acceptance target for that track
- the minimum validation expected before handoff

If three or more tracks are meant to start in parallel, add a short launch
note that says:

- which teams can start immediately
- which files or docs are single-owner seams
- which already-landed findings no team should reopen
- whether any docs-truth track is intentionally a two-pass finisher

### 6. Accept by seam first

Before broad smoke coverage, review the overlap seams:

- shared files
- replay behavior
- protocol surfaces
- fallback / escalation paths
- duplicated or newly split helpers

This catches most integration mistakes faster than rereading the entire wave.

### 7. Prove runtime behavior with a clean-room smoke

For end-to-end verification, prefer fresh-state smoke:

- rebuild or otherwise verify the runtime you are testing
- use an isolated data root or clear disposable state
- avoid inheriting old colonies, transcripts, or workspace data unless the
  test is explicitly about replay or migration
- record exactly what "clean" meant

The acceptance record should say whether the smoke validated:

- source-tree truth
- deployed/runtime truth
- replay truth

### 8. Polish only after substrate acceptance

Polish work is where you improve:

- startup flow
- naming
- docs
- UX consistency
- operator clarity

Do not smuggle architecture changes into a cleanup or polish pass.

### 9. Report what remains

Acceptance reports should classify leftover issues clearly:

- blocker
- surface-truth debt
- tuning debt
- docs debt
- runtime / deployment debt

If the substrate is truthful and replay-safe, accept it as such even if a
surface pass still remains.

### 10. Shape the next wave from what actually landed

Use the accepted state of the current wave to decide what the next one should
inherit.

Best practice:

- remove already-fixed debt from future-wave scope immediately
- keep carry-forward lists honest and bounded
- if a future wave is being drafted before the current one lands, treat that
  draft as provisional until the real leftovers are known

---

## Prompt Checklist

Use this checklist when writing coder prompts.

### Every prompt should include

- role / mission
- read-first file list
- coordination rules
- owned files
- do-not-touch list
- overlap rules
- required scope
- hard constraints
- validation commands
- whether the track can start immediately or should use a phased start

### Good prompt qualities

- grounded in current repo truth
- bounded enough to avoid merge sprawl
- honest about what data is replay-safe versus reconstructed
- explicit about whether the track owns feature work, docs work, or tests only

---

## Acceptance Checklist

Use this when integrating multi-track work.

### Seam acceptance

Confirm:

- replay behavior is sound
- no second source of truth was introduced
- protocol and route surfaces still agree with projections
- shared helpers did not fork behavior
- any event or contract changes are deliberate and mirrored everywhere

### Clean-room smoke

Record:

- how fresh state was achieved
- whether Docker / runtime was rebuilt
- what exact flow was exercised
- whether failures came from source-tree code, stale deployment, or old data

### Final report

State:

- what shipped
- what was cut
- what remains
- what the next wave should inherit, if anything

Do not carry already-fixed debt forward just because it once belonged to the
wave.

When a docs-truth track exists, expect that track to finish last more often
than first. That is healthy if it is acting as final truth integration rather
than guessing ahead of the code.

---

## Workflow-Specific Documentation Expectations

Workflow docs should evolve with the repo, not trail it by multiple waves.

When a wave lands, review:

- `docs/DEVELOPMENT_WORKFLOW.md`
- `CLAUDE.md`
- `AGENTS.md`
- `CONTRIBUTING.md`
- operator-facing runbooks
- protocol docs
- ADR index and statuses

At minimum, docs should stay truthful about:

- current event union size
- current replay / projection boundaries
- current protocol conformance
- current operator workflow
- current acceptance and smoke discipline

---

## Handoff Artifacts

At the end of a wave or major sprint, leave behind the artifacts a future
session will need:

- provisional next-wave plan, if direction was sketched before landing
- wave packet
- acceptance gates
- coder prompts
- parallel-start note, if the wave is truly parallel
- audit prompt and results
- dispatch verdict / audit verdict
- profiling report, if applicable
- session decisions memo

The goal is that a future session can start from decisions and verified repo
truth, not from transcript archaeology.

---

## Short Version

The FormicOS workflow is:

1. ground the plan in repo truth
2. decide whether the next wave is provisional or dispatch-ready
3. split the work into bounded tracks
4. write the packet
5. audit and patch the packet
6. dispatch with explicit ownership
7. accept by seam
8. verify by clean-room smoke
9. polish after substrate truth
10. report what remains without blurring categories

That discipline is what keeps fast wave execution compatible with truthful
architecture, reproducible acceptance, and maintainable docs.
