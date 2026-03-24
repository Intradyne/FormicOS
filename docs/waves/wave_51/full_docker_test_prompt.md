Wave 51 Integrator Smoke -- Fresh Docker Compose Full-Stack Test

Mission:
Prove the current repo works as a fresh deployed stack after Wave 51, not just
as source-tree truth. This is a runtime/integration acceptance pass on the
current `docker-compose.yml`, with special attention to the Wave 51 replay-safe
and UX-truth seams.

This is not a new-feature wave. It is a clean-room runtime truth check.

## Current Repo Truth To Trust

- Compose file: `docker-compose.yml`
- Default stack is 5 services:
  - `formicos-colony`
  - `formicos-llm`
  - `formicos-embed`
  - `formicos-qdrant`
  - `formicos-docker-proxy`
- Default local stack expects `local/llama.cpp:server-cuda-blackwell`
- Supported first-run path if the local image is missing:
  - `bash scripts/build_llm_image.sh`
- Main runtime smoke path:
  - `tests/smoke_test.py`
- Wave 51 final status:
  - `docs/waves/wave_51/status_after_plan.md`
- Canonical replay-safety classification:
  - `docs/REPLAY_SAFETY.md`

Wave 51 shipped and should now be treated as live truth:
- `ColonyEscalated` event added
- `QueenNoteSaved` event added
- `dismiss-autonomy` explicitly classified as ephemeral
- deprecated `/api/v1/memory/*` emits `Sunset` + `Deprecation` headers and usage logging
- "Configuration Intelligence" is the current operator-facing name
- model registry shows freshness information
- proactive briefing domain overrides are reachable inline
- `fleet-view.ts` is deleted

Do not regress already-landed Wave 50 substrate:
- global promotion is landed
- learned-template enrichment is landed

## Primary Goal

From fresh compose state:

1. bring the stack up cleanly
2. prove baseline health and existing smoke gates
3. verify Wave 51 runtime truths that are not fully covered by unit tests
4. fix any blocking runtime/deployment regressions you discover
5. rerun from fresh state if you change runtime code

## Owned Files

You may touch only what is needed to make the current compose path truthful:

- `docker-compose.yml`
- `Dockerfile`
- `tests/smoke_test.py`
- runtime/bootstrap files directly implicated by failures
- frontend files only if the failure is a real deployed-surface regression
- factual runtime docs if the live stack disproves them:
  - `docs/DEPLOYMENT.md`
  - `docs/RUNBOOK.md`
  - `docs/LOCAL_FIRST_QUICKSTART.md`
  - `docs/waves/wave_51/status_after_plan.md` only if the smoke disproves it

Do not touch:

- wave plan scope
- architecturally unrelated backend code
- caste recipes
- measurement docs
- historical audit docs just because they are stale by design

## Track A -- Clean-Room Compose Bring-Up

Treat this as fresh-state smoke.

Define "clean" explicitly in your report.

Minimum clean-up command:

`docker compose down -v --remove-orphans`

If the local llama.cpp image is missing, use the repo-supported build path:

`bash scripts/build_llm_image.sh`

Then:

1. `docker compose build formicos`
2. `docker compose up -d`
3. `docker compose ps`

## Track B -- Baseline Health

Verify all compose services are healthy/running.

Confirm these endpoints:

1. `curl http://localhost:8080/health`
2. `curl http://localhost:8008/health`
3. `curl http://localhost:8200/health`
4. `curl http://localhost:6333/collections`

If docs still claim stale service truth, fix them.

## Track C -- Baseline Smoke

Run:

`python tests/smoke_test.py`

Treat GATE failures as real until proven otherwise.

If an ADVISORY fails only because of environment/API-key/model limitations,
report it precisely instead of inflating it into a blocker.

## Track D -- Wave 51 Runtime Truth Checks

These are the important post-Wave-51 checks that should be validated against
the deployed stack.

### D1. Escalation survives replay

Prove:
- a colony can be escalated
- the escalation emits durable truth
- after restart/replay, the routing override is still present

Preferred method:
- trigger a real escalation path if practical
- otherwise use the thinnest operator/API seam that exercises the actual
  runtime event + projection path

Restart requirement:
- restart the `formicos` service (or the whole stack if needed) after the
  escalation is recorded
- verify the replayed state still reflects the escalation

### D2. Queen notes survive replay but stay private

Prove:
- a Queen note can be saved
- after restart/replay, the note is restored into Queen working context
- the operator-visible chat thread does NOT gain extra visible note rows

This is the most important Wave 51 seam check.

### D3. Deprecated Memory API signals deprecation correctly

Check at least one deprecated route, for example:
- `/api/v1/memory`
- `/api/v1/memory/search`
- `/api/v1/memory/{id}` if you have a real ID

Prove:
- `Sunset` header is present
- `Deprecation` header is present
- endpoint still serves without breaking callers

### D4. Surface-truth fixes appear in the live UI/runtime

Verify at minimum:
- "Configuration Intelligence" is the live label
- model/protocol freshness text is visible
- strategy pills do not present as clickable controls
- proactive briefing exposes domain trust/distrust/reset controls
- config-memory degraded/unavailable states render honestly if a source fails

You do not have to contrive every failure mode if it would require invasive
test harness changes, but verify as much of the shipped behavior as the live
stack reasonably exposes.

### D5. Wave 50 truths remain intact

Smoke at least one live path that would reveal regression in:
- global knowledge promotion
- learned-template surfacing

Do not accept a Wave 51 smoke that quietly broke already-landed Wave 50 truth.

## Track E -- Failure Triage

If the stack fails, inspect real deployed seams first:

1. `docker compose ps`
2. `docker compose logs formicos --tail 300`
3. `docker compose logs llm --tail 300`
4. `docker compose logs formicos-embed --tail 300`
5. `docker compose logs qdrant --tail 300`
6. `docker compose logs docker-proxy --tail 300`

Fix only what is needed to make the compose/runtime path truthful.

Prefer runtime/bootstrap fixes over speculative cleanup.

## Minimum Validation Commands

Run at minimum:

1. `docker compose down -v --remove-orphans`
2. `docker compose build formicos`
3. `docker compose up -d`
4. `docker compose ps`
5. `curl http://localhost:8080/health`
6. `curl http://localhost:8008/health`
7. `curl http://localhost:8200/health`
8. `curl http://localhost:6333/collections`
9. `python tests/smoke_test.py`

If you change Python code:

10. `python scripts/lint_imports.py`
11. `python -m ruff check src tests`
12. targeted `pytest` for the changed seam

If you change frontend runtime/UI code:

13. `cd frontend; npm run build`

## Acceptance Bar

This task is complete only if all of the following are true:

1. The stack starts from fresh state without relying on old containers/volumes.
2. Baseline health checks pass, or any host-specific blocker is documented precisely.
3. Baseline smoke passes, or any remaining failure is clearly classified.
4. Wave 51 replay-safe seams are proven in the deployed stack:
   - escalation survives replay
   - Queen notes survive replay without visible-chat pollution
5. Deprecated Memory API deprecation headers are proven live.
6. Key Wave 51 surface-truth fixes are verified against the deployed app.
7. Already-landed Wave 50 substrate is not silently regressed.

## Report Format

Return:

1. Exact commands run
2. What "clean" meant
3. Whether the local llama.cpp image had to be built
4. Which services came up healthy
5. Baseline smoke result
6. Wave 51 runtime truth result:
   - escalation replay
   - Queen note replay/private-chat check
   - deprecated Memory API headers
   - live surface checks
7. Files changed
8. Remaining issues classified as:
   - blocker
   - runtime/deployment debt
   - surface-truth debt
   - docs debt
   - advisory/model-dependent

## Important Guardrails

- Do not treat historical audit docs as current truth if live code disproves them.
- Do not reopen already-landed Wave 50 scope based on stale findings.
- Do not silently skip the Queen-note privacy check; it is a load-bearing Wave 51 seam.
- Do not call the wave accepted from unit tests alone; this is a deployed-stack check.
