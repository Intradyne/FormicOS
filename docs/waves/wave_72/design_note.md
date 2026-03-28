# Wave 72 Design Note

Four invariants govern this wave.

## 1. New action kinds, not new mechanisms or new schedulers

Knowledge review items, continuation proposals, workflow template proposals,
and procedure suggestions all flow through the existing action queue
(`action_queue.py`). The inbox (`operations-inbox.ts`) already renders by
`kind` via `_kindClass()`.

Do not create a second queue, a second inbox, or a second background loop for
these features. `app.py` should remain the single scheduler seam for the
30-minute operational cadence. New work plugs into that loop as pure helper
functions.

The existing status machine (`pending_review` / `approved` / `rejected` /
`executed` / `self_rejected` / `failed`) applies to every new kind unchanged.

## 2. Knowledge review is NOT automatic correction

The system surfaces entries for review. The operator decides. The system
never autonomously invalidates, edits, or deletes knowledge entries. Even
at `autonomous` level, knowledge mutations require human judgment.

This is the "human-in-the-loop for what the system believes" invariant.
Autonomy applies to work continuation and maintenance dispatch. It does
not apply to what the system considers true.

## 3. Prefer existing product seams over inventing parallel UI flows

Wave 72 should reuse and expose real surfaces that already exist:

- use the existing workspace ingest backend instead of inventing a second
  "docs upload" pipeline
- use the existing approve/reject action queue contract instead of a new
  review inbox contract
- use the real maintenance-policy / workspace-config path instead of fake
  settings saves

If an existing flow is hidden or unreachable, surface it in the active UI.
Do not build a duplicate.

## 4. Polish items are blockers, not nice-to-haves

The trigger wiring bug (both `docs-index` and `codebase-index` addon.yaml
manifests point manual triggers at `indexer.py::incremental_reindex` instead
of `search.py::handle_reindex`), the model-selection filtering gap, the lack
of visible document ingest on the active knowledge surface, and the Settings
structural inversion all make the product feel broken to a new user.

They ship in this wave.
