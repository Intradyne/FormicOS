# Wave 52: Learning Loop Seam Map

**Date:** 2026-03-20

End-to-end trace from task intake to future-task influence, per entry path.

---

## The Full Loop

```
Task Intake
    |
    v
Context Assembly (knowledge injection via Thompson Sampling)
    |
    v
Colony Execution (rounds, tool calls, knowledge access)
    |
    v
Access Tracing (KnowledgeAccessRecorded per round + per tool call)
    |
    v
Colony Completion (success / failure / kill)
    |
    v
Post-Colony Hooks (sequential, fire-and-forget):
    1. Observation log (structlog, no event)
    2. Step detection (workflow step tracking)
    3. Follow-up summary (async Queen notification)
    4. Memory extraction (LLM transcript scan -> candidate entries)
    5. Transcript harvest (conventions, bugs, tool configs)
    6. Confidence update (Bayesian Alpha/Beta for all accessed entries)
    7. Step completion (WorkflowStepCompleted event)
    8. Auto-template (learned template if quality >= 0.7)
    |
    v
Future Task Influence:
    - Higher-confidence entries rank higher in retrieval
    - Co-occurrence weights boost related entries
    - Learned templates shown in preview/list_templates
    - Proactive intelligence flags health issues
    - Foraging fills gaps detected during retrieval
```

---

## Per-Path Traces

### Queen Chat Path

```
Operator message
    |
    v
[PRE-SPAWN] Knowledge retrieval (last message as query)
[PRE-SPAWN] Briefing (14 deterministic rules)
[PRE-SPAWN] Config/decay recommendations
[PRE-SPAWN] Thread context + Queen notes + nudges
    |
    v
Queen LLM decides: spawn_colony / spawn_parallel
    |
    v
Colony starts -> fetch_knowledge_for_colony (top_k=5)
    |
    v
Per-round: assemble_context() injects knowledge
    |   - Budget-aware: task_knowledge 35%, observations 20%,
    |     structured_facts 15%, round_history 15%, scratch 15%
    |   - Tiered retrieval: summary -> standard -> full (auto-escalate)
    |
    v
Per-round: KnowledgeAccessRecorded (context_injection mode)
Per-tool-call: KnowledgeAccessRecorded (memory_search, knowledge_detail, transcript_search)
    |
    v
Reactive foraging check: if top score < 0.35 or < 2 sources
    |   -> background ForageService.handle_forage_signal()
    |   -> MemoryEntryCreated (candidate, conservative priors)
    |
    v
Colony completes
    |
    v
_hook_confidence_update:
    - Success: delta_alpha = min(max(0.5 + quality_score, 0.5), 1.5)
    - Mastery restoration: +20% if alpha < 0.5 * peak_alpha
    - Failure: delta_beta = 1.0 - quality_score
    - Co-occurrence: pairwise weights * 1.1 (cap 10.0)
    |
    v
_hook_memory_extraction:
    - LLM scans transcript for extractable skills/experiences
    - 5-axis credential scan
    - Entries at candidate status, Beta(5,5)
    |
    v
_hook_transcript_harvest:
    - Convention/bug/tool-config extraction
    - Feeds institutional memory admission
    |
    v
_hook_auto_template:
    - If quality >= 0.7 AND rounds >= 3 AND spawn_source == "queen"
    - AND no existing learned template for same category+strategy
    - -> ColonyTemplateCreated (learned=True)
    |
    v
Follow-up summary -> Queen sees outcome + can spawn next
```

**Learning feedback to next task:**
- Confidence-evolved entries rank differently in Thompson Sampling
- Co-occurrence weights change composite scores
- New extracted entries available for retrieval
- Foraging results available as candidates
- Learned template appears in list_templates / preview
- Proactive intelligence may flag new insights in next briefing

### A2A Path

```
External caller: POST /a2a/tasks {description}
    |
    v
[NO pre-spawn knowledge retrieval]
[NO briefing]
    |
    v
Template tag match -> classifier fallback -> defaults
    |
    v
Colony starts -> fetch_knowledge_for_colony (top_k=5)     <-- SAME
    |
    v
Per-round: assemble_context() injects knowledge             <-- SAME
Per-round: KnowledgeAccessRecorded                           <-- SAME
Reactive foraging check                                      <-- SAME
    |
    v
Colony completes
    |
    v
All post-colony hooks fire identically:                      <-- SAME
    - confidence update
    - memory extraction
    - transcript harvest
    - auto-template
```

**Key difference:** No pre-spawn intelligence. The colony itself gets
knowledge injection, but the *routing decision* (which castes, which
strategy, how many rounds) is made without consulting workspace
intelligence. The A2A caller gets classifier defaults, not
intelligence-informed defaults.

### AG-UI Path

```
External caller: POST /ag-ui/runs {task, castes?}
    |
    v
[NO pre-spawn knowledge retrieval]
[NO briefing]
[NO classification]
[NO template matching]
    |
    v
Hardcoded defaults if omitted: coder+reviewer, stigmergic
    |
    v
Colony starts -> fetch_knowledge_for_colony (top_k=5)     <-- SAME
Per-round: assemble_context() + KnowledgeAccessRecorded    <-- SAME
Reactive foraging                                          <-- SAME
Post-colony hooks                                          <-- SAME
```

**Key difference:** No intelligence in routing at all. But once the
colony is running, execution-time intelligence is identical to Queen path.

### Workflow Step Continuation

```
Prior colony completes step N
    |
    v
Queen receives follow-up with step_continuation marker
Queen sees thread context with pending steps
    |
    v
Queen decides: spawn next step colony (full Queen intelligence)
    |
    v
[Same as Queen path from here]
```

**Key observation:** Step continuation goes through the Queen, so it gets
full intelligence. This is the only "automated" path that benefits from
the full substrate.

---

## Where Knowledge Feeds Back

| Mechanism                  | Created When             | Used When                  | Active? |
|----------------------------|--------------------------|----------------------------|---------|
| Entry confidence (Alpha)   | Colony success + accessed | Thompson Sampling retrieval | YES     |
| Entry confidence (Beta)    | Colony failure + accessed | Thompson Sampling retrieval | YES     |
| Co-occurrence weights      | Colony success + multi    | Composite score (0.05)     | YES     |
| Freshness signal           | Any access               | Composite score (0.15)     | YES     |
| Thread bonus               | Entry in same thread      | Composite score (0.07)     | YES     |
| Mastery restoration        | Re-observe decayed entry | Alpha recovery bonus       | YES     |
| Extracted entries           | Post-colony LLM scan     | Future retrieval           | YES     |
| Transcript harvest          | Post-colony analysis     | Institutional memory       | YES     |
| Learned templates           | Quality >= 0.7, >= 3 rds | Preview + list_templates   | YES     |
| Reactive foraging results   | Low retrieval confidence | Future retrieval           | YES     |
| Proactive foraging results  | Maintenance cycle        | Future retrieval           | YES     |
| Distillation                | Dense clusters >= 5      | Higher-order entries       | YES     |
| Colony outcomes (projection)| Colony completion        | Performance rules only     | YES     |

---

## Where Knowledge Does NOT Feed Back

| Missing Connection                        | Impact                                   |
|-------------------------------------------|------------------------------------------|
| Outcomes do not influence routing defaults | A2A/AG-UI always get static defaults     |
| Learned templates not auto-substituted    | Queen must explicitly choose template    |
| A2A has no pre-spawn knowledge check      | Routing ignores workspace learning       |
| AG-UI has no classification               | External callers get generic defaults    |
| Performance rules not in A2A response     | External callers blind to workspace state|
| Colony outcome history not in briefing    | Queen sees outcomes only via tools       |
| Template success rates not in briefing    | Queen must call list_templates to see    |

---

## Compounding Curve

### What actually compounds over repeated tasks

1. **Retrieval quality** -- Thompson Sampling evolves confidence; entries
   that helped succeed rank higher, entries from failures rank lower.
   This is real, continuous, and event-sourced.

2. **Knowledge coverage** -- Each colony extracts skills/experiences.
   Coverage grows linearly with colonies. Gaps detected by proactive
   rules. Foraging fills external gaps.

3. **Co-occurrence structure** -- Pairwise weights between entries
   accessed together in successful colonies. Builds implicit knowledge
   graph edges over time.

4. **Learned templates** -- After quality colonies, the system captures
   what worked (castes, strategy, rounds, budget). Available for Queen
   and preview. Does not auto-apply.

5. **Proactive intelligence** -- More data means more rule triggers.
   Contradiction detection, coverage gap analysis, and merge
   opportunities all improve with more entries.

### What does NOT compound

1. **Routing decisions for non-Queen paths** -- A2A and AG-UI callers
   always get the same static defaults regardless of workspace history.

2. **Queen's spawn parameters** -- The Queen sees briefing and can
   choose to use learned templates, but nothing forces improvement.
   A careless LLM response ignores the briefing entirely.

3. **Template auto-selection** -- Learned templates are captured and
   displayed but never automatically substituted for default parameters.

---

## Summary

The learning loop is real, event-sourced, and Bayesian. Every colony
teaches the system something. But the loop primarily benefits the Queen
Chat path. Non-Queen paths contribute to learning (post-colony hooks
fire identically) but do not *benefit* from it at intake time.

The strongest compounding signal is retrieval quality via Thompson
Sampling. The weakest link is the gap between learned templates and
automatic routing improvement.
