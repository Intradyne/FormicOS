Working directory: `c:\Users\User\FormicOSa`

Audit the Wave 43 packet against the live repo. This is a seam-focused audit,
not a rewrite exercise.

Primary docs to audit:

- [wave_43_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/wave_43_plan.md)
- [acceptance_gates.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/acceptance_gates.md)
- [coder_prompt_team_1.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/coder_prompt_team_1.md)
- [coder_prompt_team_2.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/coder_prompt_team_2.md)
- [coder_prompt_team_3.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/coder_prompt_team_3.md)
- [session_decisions_2026_03_19.md](/c:/Users/User/FormicOSa/docs/waves/session_decisions_2026_03_19.md)

Important repo truth to keep in mind:

- Wave 42 is accepted.
- `docker-compose.yml` is already mature, but still mounts the raw Docker
  socket.
- `sandbox_manager.py` already has some sandbox flags, but the workspace
  executor still uses `asyncio.create_subprocess_shell(...)`.
- `store_sqlite.py` already enables WAL, but not the fuller deployment PRAGMA
  profile.
- `telemetry_jsonl.py` is still a tiny JSONL sink.
- `TokensConsumed` exists, but `projections.py` does not yet provide real
  workspace/colony budget truth.
- This wave is about production hardening, not new intelligence.
- Workspace executor isolation was explicitly elevated to Must-ship.
- OpenTelemetry should be additive beside JSONL, not a replacement-first move.
- Docker socket proxy is mitigation, not the final security story.

Read at minimum:

- [docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml)
- [Dockerfile](/c:/Users/User/FormicOSa/Dockerfile)
- [sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py)
- [store_sqlite.py](/c:/Users/User/FormicOSa/src/formicos/adapters/store_sqlite.py)
- [telemetry_jsonl.py](/c:/Users/User/FormicOSa/src/formicos/adapters/telemetry_jsonl.py)
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/runtime.py)
- [.env.example](/c:/Users/User/FormicOSa/.env.example)
- [SECURITY.md](/c:/Users/User/FormicOSa/SECURITY.md)
- [RUNBOOK.md](/c:/Users/User/FormicOSa/docs/RUNBOOK.md)

Audit goals:

1. Verify the packet is grounded in the real Wave 43 seams.
2. Check that workspace executor isolation is treated as a first-class Must.
3. Check that Team 2 is told to build budget truth before enforcement.
4. Check that observability stays additive and bounded.
5. Check that Team 3's docs work is tied to live files and honest deployment
   truth.
6. Check overlap boundaries, especially:
   - Team 1 vs Team 2 around runtime/deployment logic
   - Team 1 vs Team 3 around Compose/Docker/deployment truth
7. Flag only real blockers, misleading assumptions, or scope mistakes.

Return format:

- findings first, ordered by severity
- then a short dispatch verdict
- then the smallest set of fixes needed before dispatch, if any

What not to do:

- do not turn this into Wave 44 methodology planning
- do not relitigate Wave 42 acceptance
- do not suggest broad new architecture unless a real blocker demands it
- do not casually propose event expansion
- do not assume production hardening means a Kubernetes wave
