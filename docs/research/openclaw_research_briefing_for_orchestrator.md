# OpenClaw Codebase Research: Briefing for Orchestrator

**Source:** Deep analysis of openclaw/openclaw at HEAD, March 2026.
~325K lines TypeScript, 10K+ commits, 1000+ contributors.

**Purpose:** Extract patterns FormicOS should steal, adapt, or reject.

---

## Cloud assessment: mostly stale, one immediate win, one strategic insight

The research was written assuming FormicOS was earlier in development
(references "Wave 10-11" priorities). Most recommendations target
capabilities that already exist. But two findings are worth your
attention.

---

## Immediate action: multi-agent git safety conventions

OpenClaw's CLAUDE.md encodes battle-tested rules for multiple agents
working on the same repo simultaneously:

- No git stash unless explicitly requested
- No branch switching unless explicitly requested
- No worktree creation/deletion unless explicitly requested
- "commit" = your changes only; "commit all" = grouped chunks
- git pull --rebase to integrate, never discard others' work
- If closing >5 PRs, require explicit confirmation with exact count

**Repo truth:** The Coder caste recipe (caste_recipes.yaml line 191)
already has git_status / git_diff / git_commit / git_log from Wave
47-48, but does NOT include these safety conventions. When 3 Coder
teams work in parallel, the "commit scoping" rule is the most
important one -- it prevents agents stepping on each other's state.

**Recommendation:** Add these as guardrails in the Coder caste system
prompt. Prompt-only change, ~1 hour. Zero risk, immediate value for
parallel team dispatch.

---

## Strategic finding: what OpenClaw does NOT have

This is the most important section of the research. A 325K-line
production codebase with 1000+ contributors still lacks:

1. **No event sourcing.** State is mutable files on disk (MEMORY.md,
   session JSONLs). No append-only log, no replay, no materialized
   views. FormicOS has replay-safe event sourcing with 62 event types.

2. **No multi-agent orchestration.** Single agent per session. No
   Queen, no colony coordination. Their "multi-agent" is routing
   different channels to different isolated agents that never
   collaborate. FormicOS has Queen + caste coordination + stigmergic
   strategies.

3. **No governance engine.** No convergence checks, no stall
   detection, no approval gates. The closest thing is a simple
   allow/deny gate on tool execution. FormicOS has BudgetEnforcer,
   governance alerts, operator approval queues, stall detection with
   auto-escalation.

4. **No formal spec or ADR layer.** VISION.md is 110 lines. No wave
   packets, no constitution, no numbered design decisions. FormicOS
   has 48 ADRs, wave packets, acceptance gates, and this 148KB
   session memo.

5. **No cost optimization or model routing.** Each agent has one
   model. No cascade, no confidence-calibrated escalation, no
   local/cloud routing. FormicOS has LLMRouter with fallback chains,
   provider cooldown, per-caste model assignment, and auto-escalation
   tiers.

**What this means:** OpenClaw wins on breadth (22+ channels, 4 native
apps, massive community). FormicOS wins on depth (event sourcing,
multi-agent coordination, self-improvement, operator control). These
depth advantages are structurally harder to replicate than adding more
communication channels.

---

## Already done (no action needed)

These research recommendations target capabilities FormicOS already
has in a more sophisticated form:

**Architecture boundary tests:** Research recommends writing an AST
walker to enforce layer dependencies. FormicOS already has
lint_imports.py (114 lines) that runs in every coder validation
step. Small gap: does not yet enforce frontend types are a strict
subset of core/events.py. Worth closing but not a new effort.

**Temporal decay for retrieval:** Research recommends OpenClaw's
exponential decay with 30-day half-life. FormicOS already has:
Bayesian gamma-decay with configurable classes (ephemeral/stable/
permanent), Thompson Sampling composite scoring with freshness
weighting (_compute_freshness in knowledge_catalog.py), bi-temporal
provenance tracking (Wave 38), domain-specific decay adjustment
recommendations (Wave 37). FormicOS's version is richer.

**Pluggable context engine interface:** Research recommends
extracting a ContextAssemblerPort. core/ports.py already defines
LLMPort, EventStorePort, VectorPort, SandboxPort, and the
CoordinationStrategy protocol. The 4-layer architecture IS the
pluggable pattern. Extracting a formal context port would be a
clean refactor but not a new capability.

**Two-phase skill loading:** Research recommends OpenClaw's YAML
frontmatter (description-only for routing, body on activation).
FormicOS's Skill Bank already does description-for-retrieval +
full-body-on-match. Different mechanism, same optimization.

---

## Real gaps, not urgent

**MMR diversity re-ranking:** Genuinely missing. Thompson Sampling
optimizes relevance + exploration but not result diversity. If the
top 5 retrieval results all say the same thing, there is no mechanism
to prefer a diverse set. Worth adding when retrieval quality becomes
a bottleneck, not before.

**Config hot-reload:** Genuinely missing. But for a local-first
desktop tool where restart takes 2-3 seconds, this is quality-of-
life, not a blocker.

---

## Summary for sequencing

| Priority | Action | Effort |
|----------|--------|--------|
| Immediate | Git safety conventions in Coder prompt | ~1 hour |
| Low | Close lint_imports.py frontend-type gap | ~2 hours |
| Deferred | MMR diversity re-ranking in retrieval | ~3 hours |
| Deferred | Config hot-reload | ~6-8 hours |
| None | Everything else (already done or N/A) | -- |

---

## Bottom line

The research confirms the moat analysis from our earlier session:
FormicOS's structural advantages (event sourcing, multi-agent
orchestration, governance, formal design process, cost optimization)
are genuinely absent from the most popular production agent framework.
These are not features that can be bolted on -- they are architectural
decisions that compound over time.

The one steal worth making immediately is the git safety conventions.
Everything else is either already done better or not urgent enough to
interrupt the Wave 48-50 arc.


---

## Addendum: Refined Research (v2) -- Operational Discipline Focus

A second research pass was conducted, recalibrated against post-Wave-50
repo truth and organized around operational discipline rather than
architecture.

### Updated action items

1. **Git safety conventions** -- same as before, confirmed gap (~1 hour)

2. **Tool result head+tail truncation** -- NEW finding. runner.py line
   1417 uses head-only truncation: `text[:TOOL_OUTPUT_CAP]`. This throws
   away error messages and tracebacks at the end of tool output. FormicOS
   already has `_truncate_preserve_edges()` in context.py that keeps
   first+last halves. The fix is ~3 lines: use the existing helper for
   tool results instead of head-only. (~10 minutes)

3. **lint_imports.py frontend type check** -- same as before (~2-3 hours)

4. **Identifier preservation audit** -- DROPPED. Wave 49 compaction is
   deterministic (no LLM summarizer). Not applicable.

### Key strategic finding

OpenClaw's VISION.md explicitly lists "Agent-hierarchy frameworks
(manager-of-managers / nested planner trees) as a default architecture"
under "What We Will Not Merge." This is a conscious architectural
rejection of FormicOS's core pattern. The two projects are on
permanently divergent branches. Competitive pressure is about ecosystem
breadth (channels, apps), not architectural convergence.

### Provider error classification (file for reference)

OpenClaw has ~20 regex patterns accumulated from production failures
across 7+ providers (Anthropic, OpenAI, Google, Groq, DeepSeek,
Moonshot, etc.) that distinguish context overflow from rate limits
from billing errors. Worth bookmarking for when FormicOS expands
provider support. Not urgent.

### Item 3.1: Tool result head+tail truncation (worth stealing)

OpenClaw uses a `hasImportantTail()` heuristic: checks last 2000 chars
for error/exception/traceback/summary patterns. If found, truncates
with head+tail strategy. Constants: single tool result capped at 30%
of context window, hard limit 400K chars, minimum 2000 chars preserved.

FormicOS equivalent: use `_truncate_preserve_edges()` for tool results.
Simpler than OpenClaw's heuristic but achieves the same goal.
