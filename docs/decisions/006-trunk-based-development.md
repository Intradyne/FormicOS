# ADR-006: Trunk-Based Development with Feature Flags

**Status:** Accepted
**Date:** 2026-03-12

## Context
The v1 alpha used long-lived branches per coder stream. This created integration
failures when branches were merged — code that passed individually didn't compose.
Merge conflicts accumulated. "Is this wave done?" was ambiguous.

## Decision
Trunk-based development. Short-lived branches (hours, not days). Feature flags
wrap incomplete work so it can merge to main without breaking the build. Git
worktrees provide isolated working directories for parallel agents.

CI gates (lint, type-check, layer-check, unit tests, contract tests, feature tests)
are required for merge. GitHub merge queue tests combined changes from parallel
branches to catch integration failures.

Executable specifications (.feature files in Gherkin syntax, run via pytest-bdd)
define "done" — a wave is complete when all assigned scenarios pass.

## Consequences
- **Good:** Integration issues surface immediately (small conflict surface).
- **Good:** main is always in a working state.
- **Good:** "Done" is binary — all scenarios pass or they don't.
- **Bad:** Requires discipline to wrap incomplete work in feature flags.
- **Bad:** CI pipeline must be fast (<5 min) or it blocks developer flow.
- **Acceptable:** At alpha scale, the test suite runs in <2 minutes. Feature flags
  are simple environment variable or config file checks.

## FormicOS Impact
Affects: all development workflow. CI pipeline. AGENTS.md coordination rules.
