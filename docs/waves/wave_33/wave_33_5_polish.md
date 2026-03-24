# Wave 33.5 -- Orchestrator Dispatch: Agent Awareness + Validation Polish

## Context

Wave 33 is in final stages. Before the orchestrator validates, dispatch a
small polish pass that frontloads patterns from the Wave 35 vision into the
current codebase. These are NOT feature additions -- they are prompt rewrites,
metadata surfacing, and convention establishment that make every future wave
more effective.

The caste_recipes.yaml file tells the story: the Queen prompt is 85 lines of
thoughtful system-aware instruction. The four worker castes (coder, reviewer,
researcher, archivist) are 5-line stubs that say "you are a Coder, write code"
with zero awareness of the knowledge system, the tools they have, the
collaboration patterns they participate in, or the institutional memory
surrounding them. Every capability built since Wave 26 is invisible to the
agents executing colonies.

Use 3 parallel coder teams. Budget: 1-2 sessions each, small scope.

## Context Documents

Read before dispatching coders:
- config/caste_recipes.yaml (167 lines -- the full current prompts)
- Knowledge Pipeline Integration Reference (project knowledge)
- API Surface Integration Reference (project knowledge)
- ADR-041 (gamma-decay, composite scoring)
- ADR-042 (event union, merge semantics)
- ADR-043 (co-occurrence data model)

---

## Team 1: Worker Caste Prompt Rewrite

The four worker castes need system-aware prompts. NOT longer prompts -- more
informed prompts. Each should be 15-25 lines (up from 5), following the
Queen prompt's density and action-orientation.

### Coder prompt rewrite

The current prompt:
```
You are a Coder agent in a FormicOS colony. Your role is to:
1. Read the task description and relevant context
2. Write clean, tested implementation code
3. Run tests and fix failures
4. Report your output concisely
Follow the project's coding standards. Write tests for your code.
Commit incrementally with descriptive messages.
```

This coder has 6 tools and knows about zero of them. It participates in
a learning system and doesn't know it exists.

The rewritten prompt should include:

**Tool awareness with usage guidance:**
- memory_search: search institutional knowledge. Results have confidence
  levels -- high-confidence entries (green) are well-validated, exploratory
  entries (yellow) have fewer observations and should be treated with
  appropriate skepticism
- transcript_search: search past colony transcripts for similar approaches.
  Do NOT use for current colony data (use memory_search). Do NOT use for
  general knowledge queries (use knowledge_detail)
- knowledge_detail: get full details on a specific knowledge entry including
  confidence, provenance, and observation count
- code_execute: run code in the sandbox. All tool outputs are scanned for
  credentials -- never include real API keys or secrets in code
- memory_write: store important findings for future colonies
- artifact_inspect: examine artifacts from completed colonies

**System awareness (brief, not lecturing):**
- "Knowledge entries you access are tracked. Successful use of an entry
  increases its confidence. If an entry seems wrong or outdated, say so
  explicitly -- your assessment helps the system learn."
- "Your output will be scanned for extractable knowledge (skills, patterns,
  bug root causes). Write clear conclusions, not just code."
- "If retrieved knowledge seems irrelevant to your query, note it -- this
  helps the system detect stale entries."

**Collaboration awareness:**
- "In stigmergic colonies, your output feeds into subsequent rounds. Other
  agents (reviewer, researcher) will read what you write. Be explicit about
  decisions and tradeoffs."

### Reviewer prompt rewrite

Similar structure. Key additions beyond the coder's:
- "Your quality assessment directly influences whether extracted knowledge
  gets promoted to 'verified' status. Be specific about what works and
  what doesn't."
- "If the coder used a knowledge entry that seems outdated or incorrect,
  flag it by name. This feeds back into the knowledge system's confidence
  scoring."
- Tool list: memory_search, knowledge_detail, transcript_search,
  artifact_inspect (4 tools, no write tools -- reviewer is read-only by
  design)

### Researcher prompt rewrite

Key additions:
- "You have both memory_search (institutional knowledge) and
  transcript_search (past colony transcripts). Start with memory_search
  for established knowledge. Use transcript_search when you need to see
  how a previous colony approached a similar problem."
- "When you discover something new, use memory_write to store it. Be
  explicit about confidence: distinguish verified facts from preliminary
  findings."
- "Cite which knowledge entries you used and whether they were helpful.
  This closes the feedback loop."

### Archivist prompt rewrite

Key additions:
- "You compress colony output into durable knowledge. Each entry you create
  will be scanned for security issues and assigned a confidence prior of
  Beta(5,5). Good entries get promoted to 'verified' through successful use
  in future colonies."
- "Classify each entry with a decay_class: ephemeral (task-specific
  observations), stable (domain knowledge), or permanent (verified
  definitions). This controls how quickly confidence decays without
  re-observation."
- "Preserve precision. A vague entry ('testing is important') is noise. A
  precise entry ('async pytest fixtures must use @pytest.mark.asyncio and
  return the fixture value, not yield') is a durable skill."

### DO NOT change:
- The Queen prompt. It's being redesigned in a future wave with proactive
  intelligence. Don't touch it now.
- Tool lists (the `tools:` arrays). These are correct as-is.
- Temperature, max_tokens, max_iterations, max_execution_time_s,
  base_tool_calls_per_iteration. These are tuned.

### Acceptance criteria:
- All 4 worker caste prompts rewritten to 15-25 lines
- Each prompt lists all tools the caste has access to with 1-line usage hints
- Each prompt includes system awareness (knowledge feedback, credential
  scanning, decay classes)
- Each prompt includes collaboration context
- No prompt exceeds 30 lines (density over length)
- pytest clean, pyright clean (prompt changes don't affect code, but verify)

---

## Team 2: Retrieval Context Enrichment

When an agent calls memory_search and gets results, the results are formatted
as plain text snippets. The agent has no idea whether a result is
high-confidence or exploratory, local or federated, fresh or stale. Wave 35
will add full proactive intelligence, but the foundation is simpler: annotate
retrieval results with metadata the agent can see.

### Task 2a: Annotate memory_search results with confidence tier

In `engine/runner.py`, in `_handle_memory_search()` (the function that
formats search results for agents), add a confidence tier annotation to
each result:

Current format:
```
[Entry abc123] Python async testing patterns
  Content: Use @pytest.mark.asyncio for async test functions...
```

Enriched format:
```
[Entry abc123] Python async testing patterns
  Confidence: HIGH (verified, 47 observations)
  Content: Use @pytest.mark.asyncio for async test functions...
```

The confidence tier logic (reuse from knowledge-browser if it exists, or
implement fresh):
- HIGH: alpha+beta > 30 AND CI width < 15% AND status == "verified"
- MODERATE: alpha+beta > 15 AND status in ("verified", "active")
- LOW: alpha+beta > 10 AND status == "candidate"
- EXPLORATORY: alpha+beta <= 10 (Thompson is exploring this entry)
- STALE: prediction_error_count > 3 OR age > 90 days

Also annotate:
- Decay class if not ephemeral: "(stable)" or "(permanent)"
- Federation source if entry has foreign observations: "(includes peer data)"

This is ~20 lines of formatting code in the search result builder. The
projection data is already available -- it just isn't surfaced to agents.

### Task 2b: Annotate transcript_search results with outcome

In `surface/runtime.py`, in `make_transcript_search_fn()`, add colony
outcome to transcript search results:

Current format:
```
[Colony abc123 (completed)] Task: Build email validator
  Output snippet: Implemented EmailValidator class with...
```

Enriched format:
```
[Colony abc123 (completed, quality: 0.87)] Task: Build email validator
  Output snippet: Implemented EmailValidator class with...
  Knowledge extracted: 3 entries (2 skills, 1 experience)
```

The quality_score and skills_extracted are already on the ColonyProjection.
Surface them.

### Acceptance criteria:
- memory_search results include confidence tier (HIGH/MODERATE/LOW/EXPLORATORY/STALE)
- memory_search results include decay class and federation source when applicable
- transcript_search results include quality score and extraction count
- No new dependencies, no new events
- pytest clean (update any tests that assert on exact search result format)

---

## Team 3: Wave 33 Validation + Documentation Sync

### Task 3a: Wave 33 integration validation

Run the full Wave 33 smoke test sequence from the plan (items 1-19 in the
Smoke Test section of wave_33_plan.md). Document which items pass, which
fail, and which need fixes. This is the orchestrator's validation pass
delegated to a coder for thoroughness.

Key areas that need careful validation:
- Credential scanning: does detect-secrets actually detect sk-proj-* keys
  in mixed prose content? Test the dual-config (code vs prose) split.
- StructuredError: pick 5 high-traffic error paths (one per surface) and
  verify the full round-trip: error occurs -> StructuredError constructed
  -> mapper produces correct output -> client sees error_code +
  recovery_hint
- CRDT merge: create two ObservationCRDTs with conflicting observation
  counts. Merge. Verify query_alpha() at a specific timestamp matches
  the expected mathematical result (provide the exact computation).
- Federation: mock two-instance push/pull. Verify cycle prevention
  (instance doesn't re-replicate its own events).
- Co-occurrence: run a colony, verify co-occurrence weights are reinforced
  for accessed entry pairs. Run maintenance, verify decay applied.

For any failures: fix them in place. This team has permission to touch
any file to fix validation issues, but should document what they fixed.

### Task 3b: Documentation sync for Wave 33 changes

Verify these documents reflect the post-Wave-33 codebase:

**CLAUDE.md:**
- Event union now 53 (ADR-gated, not numerically capped)
- Credential scanning in extraction pipeline (detect-secrets, 5th axis)
- StructuredError across all 5 surfaces
- MCP resources and prompts (with transforms for Cursor/Windsurf)
- Federation architecture (CRDT, trust, conflict resolution)
- Decay classes (ephemeral/stable/permanent)
- Co-occurrence data collection (scoring deferred to 34)
- Transcript harvest at hook position 4.5

**KNOWLEDGE_LIFECYCLE.md:**
- Transcript harvest: what it extracts, where it plugs in
- Inline dedup: threshold and behavior
- Credential scanning: dual-config, 5th axis, retroactive sweep
- Prediction error counters: what they measure, how stale_sweep uses them
- Co-occurrence: reinforcement paths, decay rate, no scoring yet
- Federation: CRDT model, trust discounting, conflict resolution
- Decay classes: gamma rates per class, max_elapsed_days cap

**AGENTS.md:**
- All agent tools per caste (verify against caste_recipes.yaml tools arrays)
- New tool descriptions matching the enriched prompts from Team 1
- Federation-related information for operators

If a document doesn't exist yet, note what needs to be created. If a document
has stale content, fix it. Be specific about what changed and why.

### Acceptance criteria:
- All 19 smoke test items from wave_33_plan.md verified (pass/fail/fixed)
- CLAUDE.md accurate for post-33 codebase
- KNOWLEDGE_LIFECYCLE.md covers all Wave 33 additions
- AGENTS.md matches caste_recipes.yaml tool lists
- pytest clean, pyright clean

---

## Integration check (after all 3 teams)

- Run full pytest
- Run pyright src/
- Run lint_imports.py
- Verify caste_recipes.yaml parses correctly (no YAML syntax errors from
  prompt rewrites)
- Verify memory_search result format changes don't break any frontend
  parsing (check ws_handler.py and any frontend code that reads search
  results)
- Verify documentation is internally consistent (CLAUDE.md event count
  matches events.py, AGENTS.md tool lists match caste_recipes.yaml,
  KNOWLEDGE_LIFECYCLE.md weights match knowledge_catalog.py)
