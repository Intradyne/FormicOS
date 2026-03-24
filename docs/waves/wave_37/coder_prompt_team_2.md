# Wave 37 Team 2 - Trust Foundations + Poisoning Defense Foundation

## Role

You own the project-trust track of Wave 37.

Your job is to make FormicOS safer to adopt, safer to contribute to, and less
opaque about why it trusts the knowledge it retrieves.

This is the "make the repo and substrate externally credible" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_37/wave_37_plan.md`
4. `docs/waves/wave_37/acceptance_gates.md`
5. `docs/research/stigmergy_knowledge_substrate_research.md`
6. `.github/workflows/ci.yml`
7. `CONTRIBUTING.md`

## Coordination rules

- No new event types. The union stays at 55.
- Extend existing CI; do not replace it.
- Expand existing `CONTRIBUTING.md`; do not rewrite it from scratch.
- Some deliverables are repo-owned and some are admin-owned.
- Be explicit about that split in your docs and report.
- Team 1 shares `surface/knowledge_catalog.py` for retrieval semantics.
- Team 3 may touch `surface/knowledge_catalog.py` only if triple-tier stretch
  work lands.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `.github/workflows/ci.yml` | MODIFY | add security/scanning/provenance jobs without removing current CI truth |
| `.github/dependabot.yml` | CREATE | dependency update automation |
| `.github/ISSUE_TEMPLATE/*` | CREATE | issue templates |
| `.github/pull_request_template.md` | CREATE | PR template |
| `SECURITY.md` | CREATE | vulnerability disclosure process |
| `GOVERNANCE.md` | CREATE | project governance / succession / contribution process |
| `CODE_OF_CONDUCT.md` | CREATE | community conduct policy |
| `CONTRIBUTING.md` | MODIFY | architecture onboarding, contribution flow, admin-owned setup notes |
| `docs/GITHUB_ADMIN_SETUP.md` | CREATE | operator/admin checklist for CLA app, branch protection, labels, secrets |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | trust/provenance metadata surfacing only |
| `src/formicos/surface/routes/api.py` | MODIFY | read-only trust/provenance surfacing support only if needed |
| `frontend/src/components/knowledge-browser.ts` | MODIFY | operator-visible provenance / trust rationale display |
| `frontend/src/types.ts` | MODIFY | additive typing for surfaced rationale only if needed |
| `tests/unit/surface/test_knowledge_catalog_detail.py` | MODIFY | trust/provenance coverage |
| `tests/unit/surface/test_wave37_trust_rationale.py` | CREATE | focused trust/provenance tests |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/engine/*`
- `src/formicos/surface/projections.py` - Team 3 owns
- `src/formicos/surface/queen_runtime.py` - Team 3 owns
- `src/formicos/surface/proactive_intelligence.py` - Teams 1 and 3 own
- `src/formicos/surface/colony_manager.py` - Team 1 owns
- `src/formicos/surface/knowledge_catalog.py` retrieval/scoring semantics - Team 1 owns
- benchmark harness files - Team 1 owns

## Overlap rules

- `src/formicos/surface/knowledge_catalog.py`
  - You own trust/provenance metadata surfacing only.
  - Team 1 owns scoring/retrieval behavior.
  - If Team 3 ships Pillar 5, they own only additive triple-tier prefilter /
    staged escalation logic.
- `src/formicos/surface/routes/api.py`
  - Touch only read-only trust/provenance response shape if required.
  - Do not widen route scope into unrelated backend changes.

---

## 2A. Supply-chain security

Augment the current CI and repo with practical trust signals.

### Repo-owned deliverables

- `SECURITY.md`
- CodeQL in GitHub Actions
- Trivy container scanning in GitHub Actions
- SLSA provenance generation or documented repo-side hook-up where applicable
- SBOM generation in CI/release workflow
- Dependabot config

### Constraints

- Do not remove the existing lint/type/test/build jobs
- Keep CI understandable; do not create a maze of unreadable workflows
- If a tool requires secrets/admin setup, document the exact follow-up clearly

### Important principle

Do not optimize for badges. Optimize for:

- visible security posture
- reproducible build signals
- dependency hygiene
- clear operator/admin follow-up where repo-only setup is impossible

---

## 2B. Contributor and legal infrastructure

Expand the project's contribution surface so it is safer for outside use.

### Required scope

- harden `CONTRIBUTING.md`
- add `GOVERNANCE.md`
- add `CODE_OF_CONDUCT.md`
- add issue / PR templates
- document the CLA / DCO / branch-protection admin path

### Critical constraint

Do **not** claim CLA Assistant is fully configured unless you can prove the
repo-side and admin-side setup are both complete. In this repo, much of that is
admin-owned.

So:

- commit the repo-side pieces you can
- document the admin-owned pieces explicitly in `docs/GITHUB_ADMIN_SETUP.md`
- report the gap honestly

---

## 2C. Poisoning-defense foundation

Build the cheap substrate pieces that will be expensive to retrofit later.

### Required scope

1. Admission-scoring hooks in the ingestion path
   - pass-through behavior now
   - clean seam for stronger gating later
2. Provenance visibility
   - source colony
   - source round / source context where available
   - federation origin / peer context where available
3. Trust surfacing on retrieved entries
   - explain "why this entry is trusted"
   - do not dump only raw score math
4. Review federation trust discounting assumptions in retrieval

### Constraints

- no new event types
- keep the hook additive
- do not widen this into the full Wave 38 poisoning-defense program
- trust surfacing should help an operator read the system, not drown them

### What success looks like

An operator can inspect a retrieved entry and answer:

- where did this come from?
- why does the system trust it?
- is it local or federated?

without needing to reverse-engineer the score breakdown.

---

## Acceptance targets for Team 2

1. Existing CI is augmented with practical security/scanning posture.
2. Repo-owned contribution/legal files are committed.
3. Admin-owned follow-up is documented clearly and honestly.
4. There is a clean admission-scoring hook for future poisoning defenses.
5. Trust/provenance rationale is visible in operator-facing retrieval surfaces.
6. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If you add or edit workflow YAML, also sanity-check formatting and references by
reading the final workflow files carefully. Do not claim external GitHub app
installation or secret configuration unless it is actually complete.

## Required report

- exact files changed
- which deliverables are repo-owned vs admin-owned
- what was added to CI
- what was added to contribution/legal docs
- where the admission-scoring seam now lives
- how trust/provenance is surfaced to operators
- confirmation that no new event types were added
