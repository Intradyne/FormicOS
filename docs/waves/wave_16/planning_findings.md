# Wave 16 Planning Findings

**Date:** 2026-03-15
**Purpose:** Capture the real operator-control gaps left after Wave 15 and the repo-accurate decisions required before dispatch.

---

## 1. The bugs are real, but some root causes were mislocated

Human testing found valid product issues, but the first draft of Wave 16 pinned a few of them to the wrong seam.

### Add-thread is not frontend-only

The visible bug is the no-op handler in `frontend/src/components/formicos-app.ts`, but the repo also lacks:
- `create_thread` in frontend `WSCommandAction`
- `create_thread` in `surface/commands.py`

`Runtime.create_thread()` already exists. The real fix is a full WS surface completion, not just a button callback.

### Model classification is wrong in the snapshot builder

The operator sees the bug in the model registry UI, but the repo emits the wrong buckets in `surface/view_state.py`:
- Gemini is incorrectly allowed into `localModels`
- llama-cpp is incorrectly included in `cloudEndpoints`

The correct Wave 16 fix starts in the backend snapshot, then polishes the frontend rendering.

### `no_key` is a truthiness bug

The repo currently treats `os.environ.get(...) is not None` as "key exists". That makes an empty string look connected. Wave 16 should fix that in the snapshot/helper layer and then surface better UI guidance.

---

## 2. Thread rename is a display-name change, not an address rewrite

Current repo fact:
- `ThreadCreated.name` becomes both the projection key and the stable thread identifier

That means Wave 16 cannot safely reinterpret thread rename as an ID migration without broader contract and replay changes.

Decision:
- add `ThreadRenamed`
- keep `thread_id` stable
- update `thread.name` in projection/view only

This keeps Wave 16 small and avoids replay/address churn.

Event union:
- baseline: 35
- Wave 16: 36

---

## 3. Template authoring is mostly frontend, but not frontend-only in shape

The backend already supports:
- `template_id`
- `version`
- `tags`
- `budget_limit`
- `max_rounds`

The real gap is that the current frontend browser/editor flow does not carry enough of that shape through to support true edit/version semantics.

Decision:
- keep template authoring in Stream B
- explicitly include frontend shape work in `frontend/src/types.ts` and template-browser/editor state handling
- preserve the live flat template schema

Wave 16 should not introduce a nested governance block.

---

## 4. File I/O should stay REST + filesystem, but export must use real data sources

REST + filesystem is still the right architecture for colony file I/O.

But the first draft of Wave 16 overstated the available export model:
- there is no `agent.output` field on the live agent projection
- colony chat messages are `content` / `timestamp`, not `text` / `ts`
- code execution is not yet retained as a rich dedicated projection tree

Decision:
- upload remains REST + filesystem + `inject_message()`
- export uses uploaded files, per-round `agent_outputs`, chat transcript, and skills where feasible
- code/tool export stays conditional on what the repo actually retains cleanly

Also:
- the Wave 16 route is colony-scoped
- there is no separate pre-spawn upload workflow in this wave

---

## 5. Playbook regroup still holds

The operator feedback remains valid:
- Templates + Castes fit together as team-composition concerns
- Models should stand alone as infrastructure

ADR-028 still stands.

---

## 6. Stream shape remains good, but each stream needs audit allowance

The three-stream split still works:
- A: bugs + rename + shell/control fixes
- B: Playbook + template authoring
- C: file I/O + export

What the first draft was missing:
- permission for each stream to fix adjacent low-risk operator-facing issues in owned files

Decision:
- coders may fix clearly related paper cuts discovered in owned files
- they must not sprawl into another stream's work or open new architecture
- they must report any extra fixes explicitly

---

## 7. Overlap summary

Real overlaps:
- `formicos-app.ts`: Stream A first, Stream B second
- `colony-detail.ts`: Stream A first, Stream C second
- `frontend/src/types.ts`: Stream A first, Stream B optional second pass

Everything else is low-overlap if the ownership map stays strict.

---

## 8. What this wave should not absorb

Still out of scope:
- runtime API key hot reload
- binary uploads
- pre-spawn document staging as a separate workflow
- new colony mechanics
- dashboards
- multi-user/auth

Wave 16 is about making the existing product controllable, not expanding the system again.
