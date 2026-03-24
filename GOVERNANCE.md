# FormicOS Governance

## Project Structure

FormicOS is maintained by the Intradyne team. This document describes how
decisions are made, how contributions flow, and who has authority over what.

## Roles

### Maintainers

Maintainers have write access to the repository, can merge pull requests,
and make architectural decisions. Current maintainers are listed in the
repository's GitHub team settings.

Maintainer responsibilities:

- Review and merge pull requests
- Triage issues and security reports
- Approve Architecture Decision Records (ADRs)
- Maintain CI/CD infrastructure
- Enforce the code of conduct

### Contributors

Anyone who submits a pull request, files an issue, or participates in
discussions. Contributors do not need special permissions.

### Operator

In the context of FormicOS runtime, the "operator" is the human user who
interacts with the Queen and directs the multi-agent system. This is a
runtime role, not a governance role.

## Decision-Making

### Architectural Decisions

Significant architectural changes require an Architecture Decision Record
(ADR) in `docs/decisions/`. ADRs must be approved by at least one
maintainer before implementation begins.

The following changes always require an ADR:

- Adding or removing event types (closed union modification)
- Changing the 4-layer dependency rules
- Adding new external dependencies
- Modifying the knowledge confidence model
- Changing federation protocol semantics

### Code Changes

- All code changes go through pull requests
- PRs require at least one maintainer approval
- CI must pass before merge
- The layer boundary lint, type checker, and test suite are mandatory gates

### Event Union Changes

The event union is intentionally closed at 55 types. Adding a new event
type requires:

1. An ADR explaining why the new event is necessary
2. Maintainer approval
3. Updates to all consumers (projections, view state, contract docs)
4. TypeScript contract mirror update

## Contribution Flow

1. Open an issue or discuss in an existing thread
2. Fork the repository
3. Create a feature branch
4. Sign the CLA (see below)
5. Submit a pull request following the PR template
6. Address review feedback
7. Maintainer merges after CI passes and approval is given

## CLA / DCO

FormicOS requires a Contributor License Agreement (CLA) for external
contributions. The CLA ensures that contributions can be distributed under
the project's MIT license.

**Status**: CLA enforcement requires admin-side configuration. See
`docs/GITHUB_ADMIN_SETUP.md` for the setup steps that a repository
administrator must complete.

Until the CLA app is fully configured, maintainers will manually verify
contribution rights during PR review.

## Succession

If the current maintainer team becomes inactive:

1. Existing contributors with a track record of quality contributions may
   request maintainer access by opening an issue
2. If no response within 30 days, the project should be considered
   unmaintained
3. Forks are encouraged under the MIT license

## Code of Conduct

All participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

FormicOS is licensed under the MIT License. See [LICENSE](LICENSE) for
details.
