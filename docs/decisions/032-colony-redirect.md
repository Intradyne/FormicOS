# ADR-032: Colony Redirect for Mid-Run Goal Steering

**Status:** Accepted  
**Date:** 2026-03-15  
**Wave:** 19

## Decision

Add a `ColonyRedirected` event and a `redirect_colony` Queen tool that reframes a running colony's goal mid-run. The colony keeps its team and pheromone topology but works toward a new goal from the next round. One redirect per colony is the default, controlled by governance config.

## Context

The Queen is currently fire-and-forget. She can spawn a colony and then watch it run, but she cannot steer it once it starts drifting. If a colony heads down the wrong path, the operator either lets it burn budget until governance stops it or kills it manually.

Wave 18 gave the Queen enough visibility to inspect templates, colonies, skills, and workspace files. Wave 19 uses that visibility for the first strategic intervention: changing direction without discarding all useful progress.

The key design goal is to preserve what is still valuable:
- the original task remains auditable
- the team's communication topology remains intact
- the redirect is visible in chat and replayable in the event log

## Data Model

The colony keeps its immutable original task and gains a mutable active goal.

- `task`: original task from spawn, never overwritten
- `active_goal`: current goal used for context assembly
- `redirect_history`: append-only audit log of redirect decisions

`ColonyRedirected` carries:
- `colony_id`
- `redirect_index`
- `original_goal`
- `new_goal`
- `reason`
- `trigger`
- `round_at_redirect`

`redirect_index` stays 0-based so future multi-redirect support remains straightforward.

## Reset Semantics

On redirect:
- reset convergence progress
- clear the stall-detection window
- preserve pheromone weights
- preserve round numbering

This treats redirect as a new approach taken by the same team, not a brand-new colony.

## Governance Integration

The Queen is notified directly when governance detects a stall signal. That avoids hidden projection-only alert state. The Queen then decides whether to redirect or simply note that she is monitoring the colony.

The default safety guard is one redirect per colony, configurable through `governance.max_redirects_per_colony`.

## Skill Extraction

Skills extracted from redirected colonies should be tagged with redirect boundaries:
- `pre_redirect`
- `goal_at_extraction`

This prevents the system from learning a failed or corrected approach as if it were a clean positive pattern.

## Consequences

- the Queen becomes strategically adaptive without turning into a micromanager
- budget waste from stuck colonies decreases
- operator trust improves because redirects are visible, bounded, and auditable
- the skill bank gets cleaner signals from redirected runs

## Rejected Alternatives

### Overwrite the original task

Rejected. The original operator intent must stay recoverable for audit and debugging.

### Reset pheromones on redirect

Rejected. Pheromones encode team communication patterns, not just task-local state.

### Hide governance alerts in mutable projection state

Rejected. Important steering signals should be explicit and testable, not quietly embedded in read models.

### Include team mutation in v1 redirect

Rejected. Redirect is intentionally the smallest strategic intervention. Mid-run team mutation is more complex and belongs in a later wave.

## Implementation Note

See [algorithms.md](/c:/Users/User/FormicOSa/docs/waves/wave_19/algorithms.md).
