# Addon Extension Contract: Capability Metadata

**Type:** Compatibility note
**Date:** 2026-03-25
**Authority:** Superseded by `docs/waves/wave_68/design_note.md` and
`docs/waves/wave_68/team_c_prompt.md`

## Summary

Wave 68 keeps the addon extension contract deliberately small and additive.

Three optional manifest fields are the core contract:

```python
content_kinds: list[str] = Field(default_factory=list)
path_globs: list[str] = Field(default_factory=list)
search_tool: str = Field(default="")
```

These fields are enough to make addon coverage legible to the Queen without
adding a new registry, event type, or retrieval path.

## Routing Rule

The Queen should route by source coverage, not by hardcoded addon names.
That means:

- use `content_kinds` to identify the corpus type
- use `path_globs` to narrow the match
- use `search_tool` to identify the primary search entry point
- when an addon already exposes an obvious refresh/index trigger or handler,
  surface that in `list_addons()` text as routing guidance rather than adding
  a new core type

## Design Constraints

- additive only; existing manifests must continue to parse unchanged
- `content_kinds` stays free-form to avoid core-type churn
- capability data must appear in the text returned by `list_addons()`
- routing behavior lives in the Queen prompt/runtime, not in a new registry

## Out of Scope

- changing the core knowledge retrieval model
- automatic cross-index retrieval
- hard validation of workspace taxonomy or content kinds
