**Wave:** 43 -- "The Hardened Colony"

**Theme:** Make FormicOS deployable without lying to yourself about safety or
operations. Wave 42 built intelligence features designed to survive container
hardening; Wave 43 activates the stronger backend they were designed for.
This is the production architecture wave: container security, persistence
rules, budget governance, observability, deterministic testing, and
documentation truth for everything Waves 41-42 added.

The governing discipline for Wave 43 is simple:

- security hardening comes before visibility polish
- budget truth exists before budget enforcement
- observability is additive, not a telemetry rewrite
- deployment rules should be explicit in docs, not hidden in code
- keep the hardened backend compatible with the intelligence already landed

Wave 43 is still a build wave. Wave 44 proves. Wave 44.5 polishes.

**Prerequisite:** Wave 42 is accepted. In particular:

- static workspace analysis operates on the workspace tree without assuming a
  specific execution backend
- structural topology prior uses dependency relationships and degrades
  gracefully to fallback behavior
- contradiction resolution respects classification
- adaptive evaporation is runner-local with no surface import violation
- Wave 42 execution and workspace features were designed to survive stronger
  container isolation and deployment controls

**Contract target:** Wave 43 should harden without regressing capability.

- no new intelligence features
- no new Queen tools
- no event-union expansion unless a genuine deployment blocker proves it is
  required
- existing capabilities must keep working after hardening
- every hardening decision that matters to an operator must be documented

**The handoff sentence:** Wave 42's workspace and execution features were
designed to survive per-language containers, Sysbox/gVisor-style isolation,
and stricter budget and observability infrastructure. Wave 43 activates what
they were designed for.

---

## Current Repo Truth At Wave Start

Wave 43 should start from the current deployment and runtime seams, not from
an imagined greenfield production stack.

### What already exists

1. **Docker Compose is already production-shaped**
   - [docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml) is 225
     lines and already runs the FormicOS backend, Qdrant, llama.cpp, and the
     embedding sidecar with health checks and GPU configuration.

2. **The application image is already multi-stage**
   - [Dockerfile](/c:/Users/User/FormicOSa/Dockerfile) is 30 lines and already
     builds the frontend, installs Python dependencies with `uv`, and includes
     the Docker CLI for sandbox spawning.

3. **The raw Docker socket is still mounted**
   - [docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml#L88)
     still mounts `/var/run/docker.sock` into the backend container, with a
     comment correctly noting that this grants daemon-level access.

4. **The sandbox has some controls, but not the full hardening profile**
   - [sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py)
     already uses `--network=none`, `--memory=256m`, `--read-only`, and a
     small `tmpfs`.
   - It does **not** yet enforce capability dropping, `no-new-privileges`,
     PID limits, or a custom seccomp profile.

5. **The workspace executor is the biggest live safety gap**
   - [sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py#L177)
     currently runs repo-backed commands through
     `asyncio.create_subprocess_shell(...)` on the backend host path.
   - This is the path running `git`, tests, builds, and dependency commands
     with backend-level permissions and no container boundary.

6. **SQLite persistence exists, but deployment rules are under-specified**
   - [store_sqlite.py](/c:/Users/User/FormicOSa/src/formicos/adapters/store_sqlite.py)
     already enables WAL journaling.
   - It does **not** yet set the fuller PRAGMA profile the deployment research
     recommends, and the operator-facing docs do not yet explain the named
     volume rules clearly.

7. **Telemetry is still a lightweight debug sink**
   - [telemetry_jsonl.py](/c:/Users/User/FormicOSa/src/formicos/adapters/telemetry_jsonl.py)
     is only 24 lines and currently just appends JSONL events.
   - There is no first-class OpenTelemetry-compatible adapter yet.

8. **Budget events exist, but budget truth is thin**
   - `TokensConsumed` already exists in the event model.
   - [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py#L986)
     currently updates agent token counts on those events, but there is no
     real workspace-level or colony-level budget truth surface yet.
   - [runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/runtime.py#L197)
     already has budget-aware model routing, but not hierarchical enforcement
     or meaningful circuit breakers.

9. **Documentation is strong but still missing deployment-first guidance**
   - Existing operator and runbook docs are substantial.
   - There is still no dedicated `DEPLOYMENT.md`, no configuration reference,
     and no capacity-planning guide tying the Docker stack to actual hardware
     expectations.

### Research-validated constraints that now matter

- Workspace executor isolation is the highest-priority real safety gap.
- Docker socket proxy is a mitigation, not the final fix.
- OpenTelemetry should be added beside JSONL, not replace it first.
- Cold-start tuning should be profiling-first, not snapshot-first.
- VCR / recorded test fixtures should start small and focus on the most
  valuable LLM paths.
- This wave hardens the abstraction substrate from Wave 42 rather than adding
  new intelligence to it.

### Current hotspots relevant to Wave 43

| File | Lines | Why it matters now |
|------|-------|--------------------|
| [docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml) | 225 | deployment shape, socket mount, service boundaries |
| [Dockerfile](/c:/Users/User/FormicOSa/Dockerfile) | 30 | runtime image and sandbox coupling |
| [sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py) | 328 | sandbox flags and unsandboxed workspace execution |
| [store_sqlite.py](/c:/Users/User/FormicOSa/src/formicos/adapters/store_sqlite.py) | 120 | WAL config and persistence rules |
| [telemetry_jsonl.py](/c:/Users/User/FormicOSa/src/formicos/adapters/telemetry_jsonl.py) | 24 | additive observability seam |
| [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py) | 1405 | budget truth surface and replay timing |
| [runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/runtime.py) | 1165 | routing, enforcement, and runtime controls |
| [.env.example](/c:/Users/User/FormicOSa/.env.example) | 47 | source of truth for config documentation |

---

## Why This Wave

By the end of Wave 42, FormicOS should be more intelligent. Wave 43 makes it
safe, governable, and deployable enough that later measurement means something.

The real remaining gaps are not abstract:

1. the raw Docker socket is still too much power
2. the workspace executor still runs repo commands without isolation
3. SQLite persistence works, but the operator is not yet told the rules that
   make it safe
4. token consumption is recorded without a true workspace/colony budget
   picture or reliable circuit breakers
5. telemetry is too thin for real operations
6. CI still lacks enough deterministic recorded execution to make hardening
   work easy to defend
7. deployment documentation still assumes too much prior context

This is why Wave 43 exists. It turns the system from "intelligent in the repo"
into "deployable without pretending the risks are solved elsewhere."

---

## Pillar 1: Container Security And Execution Isolation

The highest-priority pillar. This is where the real safety gaps live.

### 1A. Sandbox container security upgrade

Upgrade the Docker sandbox execution path to use the fuller hardening profile:

- `--cap-drop=ALL`
- `--security-opt=no-new-privileges`
- `--pids-limit=256`
- larger `tmpfs` for realistic test execution
- custom seccomp profile suited to supported language runtimes

This is additive to the current `docker run` path. It should improve the
default security posture without changing the user-facing capability model.

### 1B. Workspace executor containerization

This is now a Must-ship item, not a soft follow-up.

The current workspace executor in
[sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py#L177)
is the live path for repo-backed commands, and it currently has no isolation.

Wave 43 should move that path behind a container boundary.

Preferred first version:

- run workspace commands inside a disposable container
- mount only the intended workspace directory
- apply the same core security posture as the sandbox path
- allow network only for dependency-install phases when explicitly required
- run test/build execution with network disabled afterward

Do not over-rotate into a perfect multi-runtime backend in v1. The goal is to
eliminate the unsandboxed backend-host execution path first.

### 1C. Docker socket mitigation

The raw Docker socket mount in
[docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml#L93) should no
longer be the default production story.

Short-term target for Wave 43:

- add a Docker socket proxy with a tightly restricted operation set
- document the proxy as a mitigation, not a final fix

Stretch target:

- ship a `docker-compose.sysbox.yml` or equivalent hardened variant
- document Sysbox as the recommended path for operators who want stronger
  container isolation

### 1D. Git clone security defaults

Harden repo acquisition and repo-backed execution defaults:

- no recursive submodules by default
- hooks disabled
- symlinks disabled where practical
- object verification enabled where practical
- shallow clone by default unless explicitly expanded
- clone and git operations should happen inside the isolated workspace path,
  not in the backend process

### 1E. Network-off test execution policy

The execution model should distinguish between:

- dependency acquisition or setup where network access may be needed
- actual test/build execution where network should default to off

This should ship as policy plus code, not policy alone.

---

## Pillar 2: Persistence And Cold-Start Hardening

### 2A. SQLite WAL deployment rules and PRAGMAs

Extend [store_sqlite.py](/c:/Users/User/FormicOSa/src/formicos/adapters/store_sqlite.py)
to apply the fuller deployment-oriented PRAGMA profile:

- `journal_mode=WAL`
- `synchronous=NORMAL`
- `busy_timeout=5000`
- `cache_size=-64000`
- `wal_autocheckpoint=1000`

Document the operator rules clearly:

- named volumes are the supported default
- never bind-mount the SQLite database on macOS/Windows Docker Desktop
- `.db`, `.db-wal`, and `.db-shm` must stay on the same filesystem
- FormicOS remains a single-writer backend in the supported local-first setup

### 2B. Cold-start profiling first

Do not assume replay needs snapshots just because large systems sometimes do.

Wave 43 should:

- measure actual replay / cold-start behavior on the current stack
- document the findings
- add snapshot/watermark machinery only if profiling shows it is necessary

### 2C. Qdrant persistence hardening

Confirm and document the Qdrant persistence story:

- named volume usage
- optional snapshot volume / backup path
- any `on_disk_payload` or similar tuning that is worth shipping

### 2D. Litestream evaluation

Treat Litestream as stretch evaluation work:

- verify whether it fits the local-first deployment model cleanly
- document either a viable sidecar path or a conscious rejection

Do not make the wave depend on it.

---

## Pillar 3: Budget Truth, Enforcement, And Observability

### 3A. Build budget truth first

Team 2 should not treat this as "just add circuit breakers."

The current system records token events, but the projection truth is still too
thin. Wave 43 must first build:

- workspace-level budget aggregation
- colony-level budget aggregation
- enough projection truth to explain why enforcement fired

Only then should it add stronger enforcement.

### 3B. Hierarchical budget enforcement and circuit breakers

Once budget truth exists, add bounded enforcement:

- soft warning levels
- model downgrade or similar cheaper-path controls where appropriate
- spawn throttling / queueing
- hard stop or circuit breaker for runaway cost or error conditions

Keep the enforcement logic legible and event-sourced enough that an operator
can understand what happened afterward.

### 3C. OpenTelemetry as additive instrumentation

Do **not** replace the lightweight JSONL sink first.

Add a new OTel-capable adapter beside
[telemetry_jsonl.py](/c:/Users/User/FormicOSa/src/formicos/adapters/telemetry_jsonl.py),
and instrument the most valuable seams:

- event replay timing
- event-store write latency
- retrieval latency
- LLM call duration and token usage
- colony lifecycle timing
- workspace/sandbox execution timing

The local/debug JSONL path should remain usable even if OTel is not configured.

### 3D. Cost surfaces and dashboard data

If budget truth lands cleanly, expose enough structured data for:

- workspace cost
- colony cost
- model usage mix
- budget utilization

This is useful, but it should not outrank the truth/enforcement core.

---

## Pillar 4: Testing Infrastructure Hardening

### 4A. Small VCR / recorded interaction layer

Adopt the recorded-fixture approach for the highest-value LLM paths first:

- Queen planning
- one or two execution / governance paths

Keep the first pass intentionally small. The goal is not to fixture the whole
system in one wave; it is to make the most valuable hardening paths
deterministic enough for CI.

### 4B. Regression expansion

Every meaningful failure mode found during Waves 41-43 should turn into a
targeted regression test.

This includes:

- workspace/security edge cases
- structural/topology fallback behavior
- contradiction resolution class behavior
- adaptive evaporation stability
- budget enforcement triggers

### 4C. Property-based replay tests

Add property-based coverage where it materially improves trust in the
event-sourced substrate:

- replay idempotence
- prefix replay consistency
- operator-event survival across replay

### 4D. Container-based CI checks

This is stretch unless it stays bounded.

If it lands, it should validate the hardened deployment surface itself rather
than becoming a second CI architecture.

---

## Pillar 5: Deployment Docs And Truth Pass

### 5A. Deployment guide

Create a dedicated deployment guide that explains:

- the supported Docker Compose path
- prerequisites and GPU expectations
- security posture and what is enforced by default
- SQLite and Qdrant persistence rules
- budget controls
- monitoring / observability setup

### 5B. Config reference

Document the live configuration surface from:

- [.env.example](/c:/Users/User/FormicOSa/.env.example)
- application config
- Docker Compose tunables
- security and budget defaults

### 5C. Documentation truth for Waves 41-42

Update the main reader-facing docs so they describe the real current system:

- [CLAUDE.md](/c:/Users/User/FormicOSa/CLAUDE.md)
- [AGENTS.md](/c:/Users/User/FormicOSa/AGENTS.md)
- [OPERATORS_GUIDE.md](/c:/Users/User/FormicOSa/docs/OPERATORS_GUIDE.md)
- [KNOWLEDGE_LIFECYCLE.md](/c:/Users/User/FormicOSa/docs/KNOWLEDGE_LIFECYCLE.md)
- [README.md](/c:/Users/User/FormicOSa/README.md)
- [CONTRIBUTING.md](/c:/Users/User/FormicOSa/CONTRIBUTING.md)
- [SECURITY.md](/c:/Users/User/FormicOSa/SECURITY.md)
- [RUNBOOK.md](/c:/Users/User/FormicOSa/docs/RUNBOOK.md)
- [INDEX.md](/c:/Users/User/FormicOSa/docs/decisions/INDEX.md)

### 5D. Capacity planning

Document realistic local-first deployment expectations:

- minimum supported shape
- recommended RTX 5090 local stack
- storage and event-volume expectations
- cold-start expectations once measured

---

## Priority Order (Cut From The Bottom)

| Priority | Item | Class |
|----------|------|-------|
| 1 | Sandbox security upgrade | Must |
| 2 | Workspace executor containerization | Must |
| 3 | SQLite WAL PRAGMA configuration | Must |
| 4 | Git clone security defaults | Must |
| 5 | Hierarchical budget truth + enforcement | Must |
| 6 | Docker socket proxy | Must |
| 7 | VCR fixtures (Queen planning + 1-2 paths) | Must |
| 8 | Deployment guide | Must |
| 9 | Documentation truth pass for Waves 41-42 | Must |
| 10 | Network-off test execution policy | Should |
| 11 | OpenTelemetry (additive, beside JSONL) | Should |
| 12 | Cold-start profiling (measurement first) | Should |
| 13 | Property-based event replay tests | Should |
| 14 | Qdrant persistence hardening | Should |
| 15 | Capacity planning guide | Should |
| 16 | Config reference | Should |
| 17 | Litestream evaluation | Stretch |
| 18 | Sysbox variant compose path | Stretch |
| 19 | Container-based integration checks in CI | Stretch |
| 20 | Cost reporting/dashboard data | Stretch |

---

## Team Assignment

### Team 1: Container Security + Persistence

Owns:

- Pillar 1
- Pillar 2

Primary files:

- [sandbox_manager.py](/c:/Users/User/FormicOSa/src/formicos/adapters/sandbox_manager.py)
- [docker-compose.yml](/c:/Users/User/FormicOSa/docker-compose.yml)
- [Dockerfile](/c:/Users/User/FormicOSa/Dockerfile)
- [store_sqlite.py](/c:/Users/User/FormicOSa/src/formicos/adapters/store_sqlite.py)
- seccomp profile and small deployment scripts if needed

This team owns the real deployment and isolation surface.

### Team 2: Budget Truth + Observability + Testing

Owns:

- Pillar 3
- Pillar 4

Primary files:

- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/runtime.py)
- [telemetry_jsonl.py](/c:/Users/User/FormicOSa/src/formicos/adapters/telemetry_jsonl.py)
- new additive OTel adapter if created
- targeted tests and recorded fixtures

This team owns operational truth and the deterministic hardening test layer.

### Team 3: Deployment Surface + Documentation Truth

Owns:

- Pillar 5
- operator-facing documentation of the Team 1 / Team 2 changes

Primary files:

- new `docs/DEPLOYMENT.md`
- [CLAUDE.md](/c:/Users/User/FormicOSa/CLAUDE.md)
- [AGENTS.md](/c:/Users/User/FormicOSa/AGENTS.md)
- [OPERATORS_GUIDE.md](/c:/Users/User/FormicOSa/docs/OPERATORS_GUIDE.md)
- [KNOWLEDGE_LIFECYCLE.md](/c:/Users/User/FormicOSa/docs/KNOWLEDGE_LIFECYCLE.md)
- [README.md](/c:/Users/User/FormicOSa/README.md)
- [CONTRIBUTING.md](/c:/Users/User/FormicOSa/CONTRIBUTING.md)
- [SECURITY.md](/c:/Users/User/FormicOSa/SECURITY.md)
- [RUNBOOK.md](/c:/Users/User/FormicOSa/docs/RUNBOOK.md)
- [INDEX.md](/c:/Users/User/FormicOSa/docs/decisions/INDEX.md)
- [.env.example](/c:/Users/User/FormicOSa/.env.example)

This team owns the operator and contributor understanding layer.

### Overlap

- Team 1 owns Docker/deployment mechanics; Team 3 documents them.
- Team 2 owns budget truth/enforcement; Team 3 documents the policy and
  configuration.
- Team 1 should not turn documentation comments in Compose/Docker files into
  the only place deployment rules live. Team 3 should surface those rules in
  real docs.

---

## What Wave 43 Does Not Include

- no new intelligence features
- no benchmark runs or public proof
- no compounding-curve measurement wave
- no public demos
- no learned routing or convergence prediction
- no Kubernetes implementation
- no multi-node / distributed deployment story
- no claim that socket proxying equals strong container isolation

---

## Smoke Test

1. Sandbox execution uses the stronger container security profile.
2. Workspace executor no longer runs repo-backed commands directly on the
   backend host path.
3. Git clone defaults disable the obvious unsafe behaviors.
4. SQLite opens with the fuller WAL-related PRAGMAs and the docs explain the
   named-volume rules.
5. Budget truth exists at workspace and colony level before hard stops fire.
6. At least one recorded Queen-planning fixture replays deterministically.
7. A deployment guide exists and is sufficient for a new operator to stand up
   the local-first stack.
8. The raw Docker socket is no longer the default hardened deployment story.
9. Cold-start replay behavior is measured and documented.
10. Full CI remains clean after hardening.

---

## After Wave 43

FormicOS is deployable enough that proof means something.

The container security story is stronger. The workspace execution path is no
longer the obvious backend escape hatch. Persistence rules are explicit.
Budgets have a real truth surface and real enforcement. Observability is
additive and useful. CI has a meaningful recorded interaction layer. The docs
tell the truth about how to run the system.

Wave 44 proves this hardened stack with disciplined measurement:

- forward-transfer style compounding metrics
- paired empty-vs-accumulated knowledge comparisons
- confidence intervals and multiple-run methodology
- the three public demos: live, benchmark, audit

Wave 44.5 polishes what the proof reveals, then the project publishes.

**The system measured in Wave 44 is the system hardened in Wave 43, built on
the abstractions strengthened in Wave 42 and the capability substrate landed in
Wave 41.** That causal chain is the point.
