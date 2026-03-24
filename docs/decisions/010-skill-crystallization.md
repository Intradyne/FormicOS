# ADR-010: Skill Crystallization on Colony Completion

**Status:** Proposed
**Date:** 2026-03-13

## Context

The skill bank read path works: `engine/context.py` queries `vector_port.search()`
at tier 6 and injects matching skills into agent context. But nobody writes skills.
`ColonyCompleted.skills_extracted` is hardcoded to `0`. The Archivist caste has
a system prompt mentioning `memory_write` — a tool that does not exist yet (see
ADR-007). Even with the tool wired, the Archivist only runs during rounds —
there is no post-completion extraction step.

The research is clear: skills compound faster than scale (SkillRL, Xia et al.,
2026). A 7B model with accumulated skills beats GPT-4o. The principle applies
to FormicOS: a colony that reads skills from prior successful runs will
outperform one that starts cold, regardless of model quality.

## Decision

After a colony completes successfully (`ColonyCompleted` event), the colony
manager runs a **single LLM call** to extract structured skills from the
colony's round summary. Extracted skills are upserted into the `skill_bank`
LanceDB collection. The `ColonyCompleted.skills_extracted` field is set to
the actual count.

### When Crystallization Runs

- **Only on success:** Colonies with status "completed" (not "failed" or
  "killed") trigger crystallization. Failed colonies may contain useful
  negative signal, but extracting "what NOT to do" requires different
  prompting — deferred to post-alpha.
- **After the completion event:** Crystallization runs as a fire-and-forget
  async task after `ColonyCompleted` is emitted. It does NOT block the
  colony lifecycle. If it fails, the colony is still completed — skills
  are best-effort.
- **Using the local model:** Crystallization uses the colony's own model
  assignment (usually `llama-cpp/gpt-4`). It is a structured extraction
  task — low temperature, constrained output. Local model quality is
  sufficient. No cloud call needed.

### Extraction Prompt

The prompt asks the LLM to extract transferable patterns, not task-specific
details. The output is structured JSON:

```
Given this completed colony's task and final output:

TASK: {colony.task}
FINAL OUTPUT: {last_round_summary, truncated to 2000 chars}
ROUNDS COMPLETED: {round_count}

Extract 1-3 reusable skills. Each skill must be transferable to future
colonies working on DIFFERENT tasks. Do not extract task-specific facts.

Return JSON array:
[
  {
    "technique": "Short name for the technique",
    "when_to_use": "Conditions under which this technique applies",
    "instruction": "The minimal actionable instruction for a future agent",
    "failure_modes": "What can go wrong when applying this technique"
  }
]

If no transferable skills are present, return an empty array [].
```

### Storage Schema

Each extracted skill becomes a `VectorDocument` upserted into the `skill_bank`
collection:

```python
VectorDocument(
    id=f"skill-{colony_id}-{index}",
    content=f"{skill.technique}: {skill.instruction}",  # embedded text
    metadata={
        "technique": skill.technique,
        "when_to_use": skill.when_to_use,
        "failure_modes": skill.failure_modes,
        "source_colony_id": colony_id,
        "source_task": colony.task[:200],
        "confidence": 0.5,  # initial confidence; future scoring will adjust
        "extracted_at": iso_timestamp,
    },
)
```

The `content` field (technique + instruction) is what gets embedded and
matched during retrieval. The `metadata` fields are payload for display
and filtering but do not affect semantic search.

### Retrieval Integration

The existing `context.py` retrieval path already works:

```python
skills = await vector_port.search(
    collection=colony_context.workspace_id,
    query=round_goal,
    top_k=3,
)
```

**Change required:** The collection name must use `"skill_bank"` (global)
rather than `colony_context.workspace_id` (workspace-scoped). Skills are
cross-workspace knowledge — a skill extracted from a coding colony should
be available to a research colony. Use a single `"skill_bank"` collection.

### Confidence Evolution (post-alpha)

Skills start at confidence 0.5. Future work:
- Skills from colonies with high quality scores get confidence 0.7.
- Skills that are retrieved and the colony succeeds get confidence += 0.1.
- Skills that are retrieved and the colony fails get confidence -= 0.1.
- Skills below confidence 0.2 are soft-deleted (metadata flag, not removed).

This creates a natural selection pressure on the skill bank. Not implemented
in this wave — document it for future reference.

## Consequences

- **Good:** The feedback loop closes. Colonies learn from prior successes.
- **Good:** No new event types. Uses existing `ColonyCompleted.skills_extracted`.
- **Good:** Best-effort — crystallization failure does not block colony lifecycle.
- **Bad:** The extraction LLM call adds 2-5 seconds after colony completion.
- **Bad:** Early skills (from the first few colonies) will be low quality until
  the colonies themselves produce better output.
- **Acceptable:** Even low-quality skills provide signal. The skill bank
  self-corrects as more colonies run and confidence scoring is added.

## FormicOS Impact

Affects: `surface/colony_manager.py` (crystallization step after completion),
`engine/context.py` (collection name change to `"skill_bank"`).
Reads: `core/types.py` (VectorDocument), `core/ports.py` (VectorPort, LLMPort).
