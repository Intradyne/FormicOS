# Wave 81 Team C Prompt

## Mission

Activate the existing codebase-index path for real projects and define
the canonical real-repo task pack.

This is the evaluation track for Wave 81. It gives the operator a real
codebase to index and a real set of tasks to rerun across waves.

## Owned Files

- `src/formicos/addons/codebase_index/indexer.py`
- `src/formicos/addons/codebase_index/status.py`
- `docs/waves/wave_81/real_repo_task_pack.md`
- `tests/unit/addons/test_codebase_index_status.py` (new)
- `tests/unit/addons/test_codebase_index_indexer.py` (new)

## Do Not Touch

- runtime root resolution files owned by Track A
- parallel-plan runtime files owned by Track B
- frontend components owned by Track D

## Repo Truth To Read First

1. `src/formicos/addons/codebase_index/search.py`
   The addon already uses `workspace_root_fn` and can become useful as
   soon as the root is truthful.

2. `src/formicos/addons/codebase_index/indexer.py`
   Reindex already works; the missing truth is durable status and a real
   bound project root.

3. `src/formicos/addons/codebase_index/status.py`
   The current status panel only shows chunk count / unavailable.

4. `frontend/src/components/knowledge-browser.ts`
   The product already exposes `Reindex Code`; the operator just cannot
   tell enough about what got indexed.

## What To Build

### 1. Durable code-index status

Upgrade the status path so the operator can see:

- bound root
- chunks indexed
- collection name
- last indexed timestamp
- last indexed file count
- last indexed chunk count
- last indexed error count

Recommended shape:

- write a tiny sidecar JSON file under the data dir per workspace after
  reindex
- have `status.py` merge vector-store collection info with the sidecar

### 2. Bound-root activation

Once Track A lands, reindex and search should operate on the real bound
project root automatically through `workspace_root_fn`.

Keep that seam simple. Do not duplicate project-root discovery inside
the addon.

### 3. Real-repo task pack

Write `docs/waves/wave_81/real_repo_task_pack.md`.

The task pack should:

- define 3-5 rerunnable tasks on FormicOS itself
- give each task a stable ID using `rtp-xx`
- name the files/modules involved
- define verification commands or manual acceptance checks
- be small enough to rerun after Wave 81 and again after Wave 82

## Important Constraints

- Do not add import-graph population yet
- Do not add learned-pattern storage here
- Do not turn the task pack into a giant benchmark program

## Validation

Add focused tests that prove:

1. status reports bound-root + last-indexed truth when metadata exists
2. status degrades cleanly when no metadata or no vector store exists
3. reindex sidecar data is written deterministically

Run:

- `python -m pytest tests/unit/addons/test_codebase_index_status.py -q`
- `python -m pytest tests/unit/addons/test_codebase_index_indexer.py -q`

## Overlap Note

You are not alone in the codebase. Track D will render your status truth
in multiple places. Keep the status payload small and deterministic so
the frontend can reuse it cleanly.
