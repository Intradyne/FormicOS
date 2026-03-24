## Summary

Brief description of what this PR does and why.

## Changes

- [ ] Change 1
- [ ] Change 2

## Architecture Checklist

- [ ] Read relevant ADRs in `docs/decisions/` before making architectural choices
- [ ] No new event types added (or ADR approved for new events)
- [ ] Layer boundaries respected (`python scripts/lint_imports.py` passes)
- [ ] No files outside my ownership modified (check `AGENTS.md` if wave-dispatched)
- [ ] Contracts in `docs/contracts/` not modified without approval

## Testing

- [ ] `uv run ruff check src/` passes
- [ ] `uv run pyright src/` passes
- [ ] `python scripts/lint_imports.py` passes
- [ ] `python -m pytest -q` passes
- [ ] `cd frontend && npm run build` passes (if frontend changes)

## Related Issues

Closes #

## Notes for Reviewers

Any context that helps reviewers understand the changes.
