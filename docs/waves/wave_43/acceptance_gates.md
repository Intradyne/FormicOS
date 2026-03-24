This document compresses the Wave 43 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- [wave_43_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_43/wave_43_plan.md)

---

## Must Ship

### Gate 1: The execution surface is materially safer

All of the following must be true:

1. Sandbox execution uses a stronger container security profile than before.
2. The workspace executor is no longer just an unsandboxed backend-host shell
   path for repo-backed work.
3. Git clone defaults close the obvious hook/submodule/symlink risks.
4. The raw Docker socket is no longer the only supported hardened story.

Passing evidence:

- stronger sandbox flags or seccomp controls are visible in the execution path
- workspace execution is isolated behind a container boundary or equivalent
  bounded mechanism
- Git safety defaults are explicit
- socket proxying or an equivalent mitigation is real and documented honestly

### Gate 2: Persistence rules are truthful and deployable

All of the following must be true:

1. SQLite opens with a fuller WAL-oriented PRAGMA policy.
2. The operator-facing docs explain the named-volume rules and the
   macOS/Windows bind-mount hazard.
3. Qdrant persistence expectations are documented clearly enough to operate.
4. Cold-start behavior is measured rather than guessed.

Passing evidence:

- the SQLite adapter sets the intended PRAGMAs
- deployment docs explain the filesystem rules
- cold-start findings are documented, even if no optimization was needed

### Gate 3: Budget truth exists before strong enforcement

All of the following must be true:

1. Workspace-level and colony-level budget truth exists in a projection or
   equally inspectable runtime truth surface.
2. Any circuit breaker or hard-stop behavior is explainable from that truth.
3. The system can stop obvious runaway spend or error loops.
4. The budget path remains operator-legible rather than becoming opaque policy.

Passing evidence:

- projections or equivalent surfaces show budget aggregates
- enforcement triggers are explainable
- at least one runaway-budget path is actually blocked

### Gate 4: Deterministic hardening tests improve

All of the following must be true:

1. Recorded / replayable fixture coverage exists for at least the highest-value
   LLM paths.
2. Wave 43 hardening paths gained regression coverage.
3. Replay / event-sourced correctness trust improved rather than regressed.
4. CI does not depend on live LLM calls for these new assurances.

Passing evidence:

- small VCR-style fixtures exist
- regression tests cover the new deployment/security behavior
- live-LLM dependence did not expand in CI

### Gate 5: Deployment docs tell the truth

All of the following must be true:

1. A deployment guide exists.
2. Configuration surfaces are documented from real files, not memory.
3. Security posture is described honestly, including mitigations vs true fixes.
4. Waves 41-42 features are described accurately in the main docs.

Passing evidence:

- deployment/config docs exist and are sufficient to stand up the system
- socket proxy vs Sysbox language stays honest
- the docs reflect the current post-Wave-42 system

---

## Should Ship

### Gate 6: Observability gets better without replacing the simple path

If OpenTelemetry or similar observability lands, it should:

1. remain additive beside the JSONL sink
2. cover the most valuable runtime seams first
3. avoid turning Wave 43 into a telemetry rewrite

### Gate 7: Cold-start optimization only lands if profiling justified it

If snapshots, watermarks, or replay optimizations land, they should:

1. be motivated by actual profiling
2. remain bounded
3. avoid speculative infrastructure churn

### Gate 8: Container hardening remains compatible with Wave 42 capability

The hardened backend should preserve:

1. workspace-aware capability
2. multi-file execution flows
3. the ability of Wave 42 intelligence features to operate under the new
   deployment model

---

## Stretch

### Gate 9: Litestream, Sysbox, or deeper deployment paths only if bounded

Stretch deployment improvements are welcome only if they:

1. do not destabilize the core hardening work
2. remain honest about maturity
3. leave the default deployment path simpler, not more confusing

---

## Cut Line

Cut from the bottom in this order:

1. Litestream evaluation
2. Sysbox variant compose path
3. container-based CI extras
4. cost/dashboard surfaces
5. non-essential observability breadth

Do **not** cut:

- workspace executor isolation
- SQLite deployment truth
- budget truth before enforcement
- small deterministic fixture coverage
- deployment documentation

---

## Final Acceptance Statement

Wave 43 is accepted when FormicOS can honestly claim:

- the execution surface is materially safer
- the persistence story is real and documented
- budgets are inspectable and enforceable
- deterministic hardening tests exist
- deployment docs tell the truth
