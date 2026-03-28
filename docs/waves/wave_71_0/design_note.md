# Wave 71 Design Note: Operational State

Wave 71 adds an operational layer above plans, session summaries, and
proactive intelligence. That layer exists to keep the Queen coherent across
days while staying legible to the operator. These invariants apply to both
71.0 (substrate) and 71.5 (surface).

## Invariants

1. Operational state is not institutional memory.

- Do not store journals, procedures, or queued actions in `memory_entries`.
- `memory_entries` remain distilled reusable knowledge.
- Operational state is file-backed working memory and audit history.

2. The live approval system stays event-sourced.

- Use the existing `ApprovalRequested`, `ApprovalGranted`, and
  `ApprovalDenied` path for pending human gates.
- The new action ledger is a durable audit/history layer, not a second
  approval authority.

3. Existing artifacts remain primary sources.

- Thread plans stay in `.formicos/plans/{thread_id}.md`.
- Session summaries stay in `.formicos/sessions/{thread_id}.md`.
- Project plan stays in `.formicos/project_plan.md`.
- The new operational layer references and synthesizes them; it does not
  replace them.

4. Every autonomous action must leave an audit trail.

- Proposed, executed, rejected, and self-rejected actions must be queryable.
- If the operator asks "what happened while I was away?", the answer should be
  recoverable without replaying internals by hand.

5. The action queue is generic, not maintenance-specific.

- `actions.jsonl` is the universal operational inbox for future action kinds:
  continuation, knowledge review, workflow-template proposal,
  procedure suggestion, and similar items.
- The durable action `kind` is the semantic authority for routing and UI.
- Any legacy approval transport details are implementation detail, not product
  semantics.

## New File-Backed Operational Layer

Use workspace-scoped operational files:

- `.formicos/operations/{workspace_id}/queen_journal.md`
- `.formicos/operations/{workspace_id}/operating_procedures.md`
- `.formicos/operations/{workspace_id}/actions.jsonl`

This keeps operational state separate from global project files while still
letting the operator open and edit the human-facing artifacts directly.

## Queen Context Contract

The Queen should read concise operational context on every response:

- operating procedures
- recent journal tail
- prior session summary
- project plan
- compact continuation/sync summary

This context must be budgeted explicitly. Hardcoded char caps are acceptable
only as fallback floors, not as the primary policy.

The operational summary should also expose operator-availability truth now:

- last operator activity timestamp
- idle duration / active-vs-idle signal
- whether a continuation candidate is ready, blocked, or review-only

## Wave Boundary

Wave 71.0 lands the substrate and machine-readable seams.
Wave 71.5 turns them into a dedicated Operations surface.
Wave 72 can then hang knowledge review and workflow-template proposals off the
same action queue instead of inventing another operator workflow.
