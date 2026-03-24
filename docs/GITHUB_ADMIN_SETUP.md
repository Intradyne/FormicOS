# GitHub Admin Setup Checklist

This document lists the admin-owned configuration steps that cannot be
committed as code. A repository administrator must complete these manually.

## Branch Protection

1. Go to **Settings > Branches > Branch protection rules**
2. Add a rule for `main`:
   - [x] Require a pull request before merging
   - [x] Require approvals (minimum 1)
   - [x] Require status checks to pass before merging
     - Required checks: `lint`, `typecheck`, `layer-check`, `test`,
       `frontend-build`, `build`
   - [x] Require branches to be up to date before merging
   - [x] Do not allow bypassing the above settings

## CLA Assistant

FormicOS requires a Contributor License Agreement for external
contributions.

### Option A: CLA Assistant (GitHub App)

1. Install [CLA Assistant](https://github.com/apps/cla-assistant) on the
   repository
2. Configure with a CLA document (draft a simple MIT-compatible CLA)
3. The app will automatically check PRs for CLA signatures

### Option B: DCO (Developer Certificate of Origin)

Alternatively, require DCO sign-off on commits:

1. Install [DCO GitHub App](https://github.com/apps/dco)
2. Contributors must add `Signed-off-by: Name <email>` to commits
3. The app blocks PRs without proper sign-off

**Current status**: Neither is configured. Until one is set up,
maintainers must manually verify contribution rights during PR review.

## GitHub Labels

Create these labels for issue triage:

| Label | Color | Description |
|-------|-------|-------------|
| `bug` | `#d73a4a` | Something isn't working |
| `enhancement` | `#a2eeef` | New feature or request |
| `dependencies` | `#0366d6` | Dependency updates |
| `security` | `#e11d48` | Security-related |
| `good-first-issue` | `#7057ff` | Good for newcomers |
| `core` | `#fbca04` | Affects core layer |
| `engine` | `#fbca04` | Affects engine layer |
| `surface` | `#fbca04` | Affects surface layer |
| `frontend` | `#1d76db` | Frontend changes |
| `docs` | `#0075ca` | Documentation |
| `wave-N` | `#bfd4f2` | Wave-specific work |

## Security Scanning Secrets

The security workflow (`security.yml`) uses these GitHub features:

- **CodeQL**: Works out of the box with GitHub Advanced Security (free for
  public repos)
- **Trivy**: No secrets required; uses public vulnerability databases
- **SBOM (Syft)**: No secrets required
- **SLSA Provenance**: Requires `id-token: write` permission (configured
  in workflow). Full SLSA Level 3 requires additional setup:
  - Enable "Artifact Attestations" in repository settings
  - The workflow uses `actions/attest-build-provenance@v2`

## Dependabot

Dependabot configuration is committed to `.github/dependabot.yml` and
should activate automatically. Verify in **Settings > Code security and
analysis** that Dependabot is enabled.

## Repository Settings

Recommended settings:

- **Settings > General > Features**:
  - [x] Issues enabled
  - [x] Discussions enabled (optional, for community Q&A)
  - [ ] Wiki disabled (docs live in-repo)
- **Settings > Code security and analysis**:
  - [x] Dependency graph enabled
  - [x] Dependabot alerts enabled
  - [x] Dependabot security updates enabled
  - [x] Code scanning (CodeQL) enabled
  - [x] Secret scanning enabled
