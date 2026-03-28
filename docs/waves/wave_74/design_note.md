# Wave 74 Design Note — Queen Command & Control

## Purpose

Wave 74 transforms the Queen tab from a fleet dashboard ("what's happening?")
into a command surface ("what does the Queen want from me, what is she doing,
what rules is she following, how is she performing?"). The colonies don't
disappear — they move to the Workspace view where they belong. The Queen tab
becomes about the Queen herself.

## Invariants

### 1. The display board extends the journal, not a new storage layer

Event types are a closed union (69 events). The display board stores structured
observations via `append_journal_entry()` with extended heading/metadata fields.
No new event types. The `queen-journal-panel.ts` frontend component already
expects a `{timestamp, heading, body}` shape — the backend catches up. Any
metadata comment lines added for display-board filtering are parser/UI-only and
must be stripped from Queen prompt injection (`read_journal_tail()` /
`render_journal_for_queen()`) so the Queen does not see HTML comment noise.

### 2. Behavioral overrides use existing `WorkspaceConfigChanged` events

Queen behavioral overrides (`queen.disabled_tools`, `queen.custom_rules`,
`queen.team_composition`, `queen.round_budget`) are workspace config fields
stored via `WorkspaceConfigChanged`. Read path:
`projections.workspaces[ws_id].config["queen.*"]`. Injected into the Queen's
context in `_build_messages()` as a system block after the base system prompt.

### 3. Tool tracking is session-scoped, not persisted

Queen tool call counts live in memory on the QueenRuntime instance. They reset
on restart. The journal already captures what happened — the counter is for
live operational insight, not audit.

### 4. Tool inventory is self-assembled, not manually authored

The Queen's system prompt tool section has drifted (recipe says 36, actual
tool surface is 41+). Wave 74 fixes this permanently: the `## Tools` section
in `caste_recipes.yaml` becomes a `{TOOL_INVENTORY}` placeholder, replaced at
runtime in `_build_messages()` with the live list from
`self._tool_dispatcher.tool_specs()`. This covers all three tool sources:
`_handlers` dict, special-cased tools (`archive_thread`, `define_workflow_steps`),
and dynamically appended addon tools. After this wave, adding a Queen tool
never requires updating a manual tool list. The count is always correct.

### 5. Elevation first, invention second

74.0 makes visible what's already computed (continuation candidates, autonomy
score, context budget, procedures). 74.5 adds genuinely new capabilities
(display board posting, tool tracking, behavioral overrides). The Queen tab
is useful after 74.0 alone; 74.5 makes it interactive. `queen-overview.ts` is
the single composition shell for the Queen tab: Teams B and C ship components
and data contracts, Team A mounts them.

## What Wave 74 does NOT do

- No new event types (stays at 69)
- No changes to the Queen's system prompt prose in `caste_recipes.yaml` (tool inventory section becomes a runtime placeholder)
- No changes to `queen_budget.py` fractions (visualization only)
- No changes to `projections.py` event handlers (uses existing config projection)
- No changes to `addon_loader.py`, `events.py`, or `knowledge_catalog.py`
- No context budget tunability (read-only visualization; tuning is a future ADR)
- No persistent tool usage analytics (session-scoped counters only)

## The four-question layout

The Queen tab answers four questions in visual priority order:

1. **What does she want from me?** — Display board with attention/urgent items
2. **What is she doing?** — Active work, continuation candidates, current goals
3. **What rules is she following?** — Operating procedures, autonomy level, overrides
4. **How is she performing?** — Trust score, tool usage, knowledge health, budget

## Post-wave state

| Surface | Before 74 | After 74 |
|---------|-----------|----------|
| Queen tab sections | 14 (fleet-centric) | 6 (Queen-centric) |
| Display board | None | Journal-backed structured observations |
| Behavioral overrides | None | 4 workspace-scoped override keys |
| Tool usage visibility | None (addon counts only) | Session-scoped Queen tool counters |
| Context budget visibility | None | 9-slot stacked bar visualization |
| Autonomy score in UI | Level only (suggest/auto_notify/autonomous) | Full grade (A-F), 4 components, recommendation |
| Continuation candidates in UI | None (Queen-internal only) | Visible list with readiness/blockers |
| Colony cards | Queen tab | Workspace view |
| Queen tools | 41 | 42 (+post_observation), self-assembled inventory |
