## Role

You own the container security, workspace isolation, and persistence track of
Wave 43.

Your job is to:

- materially harden code execution
- remove the obvious unsandboxed workspace-execution hole
- tighten the persistence/deployment substrate without regressing capability

This is the "make execution survivable in production" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_43/wave_43_plan.md`
4. `docs/waves/wave_43/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `docker-compose.yml`
7. `Dockerfile`
8. `src/formicos/adapters/sandbox_manager.py`
9. `src/formicos/adapters/store_sqlite.py`
10. `docs/RUNBOOK.md`
11. `SECURITY.md`

## Coordination rules

- Workspace executor isolation is a Must-ship item, not a soft follow-up.
- The raw Docker socket is not an acceptable default hardened story.
- Docker socket proxying is a mitigation, not the final fix.
- Keep the first version of workspace isolation simple and bounded.
- Do **not** undo or bypass Wave 41/42 capability to make security easier.
- Prefer additive hardening over architecture churn.
- Cold-start work is profiling-first. Do **not** invent snapshot machinery
  unless the measurements justify it.
- Do **not** add event types unless you hit a real deployment blocker and can
  prove it.
- Do **not** turn this into a Kubernetes wave.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `docker-compose.yml` | OWN | socket mitigation, hardened deployment defaults |
| `Dockerfile` | OWN | runtime image / isolated execution support if needed |
| `src/formicos/adapters/sandbox_manager.py` | OWN | stronger sandbox profile + isolated workspace execution |
| `src/formicos/adapters/store_sqlite.py` | OWN | fuller WAL-oriented PRAGMA policy |
| `scripts/` | MODIFY/CREATE | bounded deployment helpers only if needed |
| `config/` or deployment assets | MODIFY/CREATE | seccomp profile or related bounded assets |
| `tests/` | CREATE/MODIFY | hardening, workspace-isolation, and persistence tests |

## DO NOT TOUCH

- `src/formicos/surface/projections.py` - Team 2 owns budget truth
- `src/formicos/surface/runtime.py` - Team 2 owns budget enforcement
- `src/formicos/adapters/telemetry_jsonl.py` - Team 2 owns observability path
- docs and wave packet files - Team 3 owns documentation truth
- intelligence/runtime-control seams from Waves 41-42 - out of scope

---

## Pillar 1: Container security and execution isolation

### Required scope

1. Harden the sandbox container profile materially.
2. Move workspace executor commands behind an isolation boundary.
3. Add safe git-clone defaults for repo-backed work.
4. Replace the raw-socket-only story with a tighter default deployment path.

### Hard constraints

- Do **not** leave `execute_workspace_command()` as an unsandboxed host-shell
  path and still claim Wave 43 is hardened.
- Do **not** make workspace isolation depend on a fully perfect multi-language
  image matrix in v1.
- Do **not** overclaim socket proxying as equivalent to Sysbox or strong
  container isolation.
- Do **not** make the default developer path significantly harder unless the
  security benefit clearly justifies it.

### Guidance

- Start by containing the existing workspace execution path.
- The workspace executor is called via
  `colony_manager.py:_build_workspace_execute_handler()` with a
  `(command, working_dir, timeout_s)` signature. Keep that interface stable if
  possible. If you must change it, call the change out explicitly in your
  summary for Team 3 docs and coordination.
- Keep network access phase-aware if you need it:
  - dependency/setup phase may require bounded network
  - actual test/build execution should prefer network-off
- If you add a seccomp profile, keep it understandable and documented.

---

## Pillar 2: Persistence and cold-start hardening

### Required scope

1. Extend SQLite configuration to a fuller deployment-safe WAL profile.
2. Make the deployment filesystem rules explicit in code comments where useful,
   but do not rely on comments alone for truth.
3. Measure cold-start / replay behavior on the current stack.

### Optional scope

Only if justified by measurement:

- bounded replay optimization
- bounded Qdrant persistence refinements
- bounded Litestream evaluation
- bounded Sysbox variant compose path

### Hard constraints

- Do **not** add snapshot/watermark machinery speculatively.
- Do **not** broaden this track into distributed or multi-node persistence.
- Do **not** push deployment truth into docs only; code should reflect the
  intended SQLite policy directly.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for sandbox, workspace execution, and SQLite seams
3. full `python -m pytest -q` if your execution or persistence changes broaden
   into shared runtime behavior

If you add container-based checks, keep them bounded and clearly separate from
the minimum test path.

## Developmental evidence

Your summary must include:

- how the workspace executor is now isolated
- what security flags/profiles were added to container execution
- what git safety defaults now apply
- what SQLite PRAGMAs now apply
- what cold-start profiling showed
- what you rejected to keep the hardening bounded and honest
