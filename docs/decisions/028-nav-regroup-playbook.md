# ADR-028: Nav Regrouping — Playbook Tab Replaces Fleet

**Status:** Accepted (supersedes ADR-027)
**Date:** 2026-03-15
**Context:** Wave 16. Feedback from first real operator testing.

---

## Decision

Replace the "Fleet" tab (Models + Castes) with:
- **Playbook** tab: Templates + Castes (team composition)
- **Models** tab: standalone (infrastructure)

Nav becomes: Queen, Knowledge, Playbook, Models, Settings.

## Why ADR-027's grouping was wrong

ADR-027 merged Models + Castes into "Fleet" based on the reasoning that both concern the agent compute layer. After real usage, the operator reported that colony templates and caste definitions feel more related to each other than models and castes.

This is correct:
- **Templates** = "what team do I deploy" (composition, governance, budget)
- **Castes** = "what kinds of agents exist" (roles, tools, prompts)
- **Models** = "what compute is available" (endpoints, API keys, costs)

Templates and castes are co-configured when designing a colony. Models are infrastructure set up once and rarely changed during normal operation. Grouping by workflow frequency, not by architectural layer, serves the operator better.

## Implementation

- Rename `fleet-view.ts` to `playbook-view.ts`
- Change sub-tabs from Models/Castes to Templates/Castes
- Models tab renders `model-registry` directly
- Update NAV array in `formicos-app.ts`

## Alternatives considered

**Keep Fleet, add Templates as third sub-tab:** Three sub-tabs in one tab is too crowded. The operator would need two clicks to reach templates.

**Merge all three (Models + Castes + Templates) into one tab:** Too much in one view. The operator's mental model separates "what I deploy" from "what infrastructure I have."
