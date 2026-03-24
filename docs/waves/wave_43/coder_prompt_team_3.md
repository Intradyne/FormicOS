## Role

You own the deployment surface and documentation-truth track of Wave 43.

Your job is to:

- turn the hardened backend into an operator-readable deployment story
- document the real configuration and safety rules
- update the main docs so they describe the post-Wave-42 / Wave-43 system
  honestly

This is the "operators and contributors can actually deploy this correctly"
track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_43/wave_43_plan.md`
4. `docs/waves/wave_43/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `docker-compose.yml`
7. `Dockerfile`
8. `.env.example`
9. `SECURITY.md`
10. `docs/RUNBOOK.md`
11. `docs/OPERATORS_GUIDE.md`
12. `docs/KNOWLEDGE_LIFECYCLE.md`
13. `README.md`
14. `CONTRIBUTING.md`
15. `docs/decisions/INDEX.md`

## Coordination rules

- Deployment truth must live in real documentation, not only in code comments.
- Be explicit about mitigations vs stronger fixes:
  - socket proxy is mitigation
  - Sysbox/gVisor-style isolation is stronger
- Document the supported path first. Do not bury it under optional variants.
- Use live files as the config source of truth, not memory.
- Keep this guide public-facing and operator-friendly rather than internal-only.
- Do **not** invent features the code does not actually ship.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `docs/DEPLOYMENT.md` | CREATE | deployment guide |
| `CLAUDE.md` | MODIFY | post-Wave-43 repo truth |
| `AGENTS.md` | MODIFY | current tool/surface truth as needed |
| `README.md` | MODIFY | capability + deployment truth |
| `CONTRIBUTING.md` | MODIFY | contributor-facing setup/test truth only |
| `SECURITY.md` | MODIFY | deployment and execution hardening truth |
| `docs/RUNBOOK.md` | MODIFY | common operations and recovery procedures |
| `docs/OPERATORS_GUIDE.md` | MODIFY | operator-facing hardening and budget controls |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | only if Wave 43 changes touch knowledge truth |
| `docs/decisions/INDEX.md` | MODIFY | decision index truth |
| `.env.example` | MODIFY | config surface comments and clarity |

## DO NOT TOUCH

- Docker/execution implementation files - Team 1 owns
- runtime/projection/telemetry logic - Team 2 owns
- wave packet docs after dispatch, unless explicitly asked for a docs-only fix

---

## Pillar 5: Deployment docs and truth pass

### Required scope

1. Create a real deployment guide.
2. Document the live configuration surface from actual files.
3. Explain the hardened execution and persistence posture honestly.
4. Update the main docs so they match Waves 41-43 reality.

### Hard constraints

- Do **not** tell a stronger security story than the code actually supports.
- Do **not** let Compose comments be the only place critical deployment rules
  exist.
- Do **not** reintroduce internal AI workflow material into public-facing
  contributor docs.
- Do **not** assume operators already understand Docker Desktop filesystem
  caveats, GPU setup, or budget controls.

### Guidance

- Put the supported local-first path first.
- Call out the SQLite named-volume rule prominently.
- Call out socket-proxy mitigation vs stronger isolation clearly.
- Include enough config detail that a new operator can go from clone to running
  stack without guessing.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py` only if you happen to touch code-adjacent
   files with import implications
2. any relevant doc-link or build checks if they already exist
3. targeted smoke verification against the files you documented

You do **not** need to turn this into a product test run unless your docs work
depends on it.

## Developmental evidence

Your summary must include:

- what deployment/config docs were created or updated
- what security/persistence rules are now explicit for operators
- what Wave 41-42 truth was corrected in the docs
- any places where the code is still weaker than the ideal deployment story
