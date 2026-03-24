# Research Prompt: Five Strategic Dimensions for FormicOS Post-Wave-48

## Context

FormicOS is an event-sourced, local-first, multi-agent colony framework with:
- Queen coordinator + specialist castes (Coder, Reviewer, Researcher, Forager, Archivist)
- Stigmergic pheromone-weighted topology routing
- Active knowledge acquisition via Forager service (web search, content quality scoring, source credibility)
- Replay-safe event-sourced architecture (62 event types, SQLite WAL)
- Operator-editable knowledge with pin/mute/invalidate, competing hypotheses, confidence decay
- Surgical code editing (patch_file), fast_path for simple tasks, git tools
- Thread-level audit timeline (post-Wave-48)
- Local inference (Qwen3-30B-A3B on RTX 5090) + cloud escalation (Anthropic/OpenAI)
- ~39K backend, ~12K frontend, 3,254 tests passing

What we already know well (DO NOT re-research):
- Self-evolution taxonomy (Fang et al., Gao et al. surveys)
- Configuration-space search as the improvement surface
- Intrinsic vs extrinsic metacognition (ICML 2025 position paper)
- Pheromone routing, DyTopo, GPTSwarm topology optimization
- The research colony / experimentation engine architecture (conceptual)
- Context window management, KV-cache optimization
- Tool design patterns (SWE-agent ACI, Aider, Claude Code)
- Memory hierarchy (Generative Agents, MemGPT/Letta, Voyager)

What we need: practical implementation patterns, failure modes, and
empirical evidence for the five dimensions that are furthest from
realization in the current system.

---

## Dimension 1: Ambient and Proactive Intelligence

FormicOS currently has a maintenance briefing loop (runs on a timer,
checks for staleness, coverage gaps, contradictions) and a Forager that
can proactively fill knowledge gaps. But it is not ambient -- it doesn't
monitor the operator's world and suggest actions unprompted.

### What to search for

**Q1.1: CI/CD and repository monitoring patterns in AI coding assistants**

How do production systems (Devin, Cursor background agents, GitHub Copilot
Workspace, Amazon CodeWhisperer) monitor external signals and proactively
suggest work?

- Does Devin monitor CI status and proactively offer to fix failing builds?
- Do Cursor's "background agents" watch for events and trigger work?
- How does GitHub Copilot Workspace handle "ambient awareness" of repo state?
- What event sources do these systems subscribe to (webhooks, polling, file watchers)?
- What's the UX pattern for surfacing proactive suggestions without being annoying?

Search: "Devin proactive CI monitoring 2025 2026", "Cursor background agent
trigger", "GitHub Copilot Workspace ambient awareness", "AI coding assistant
proactive suggestions UX", "Devin 2.0 autonomous monitoring"

**Q1.2: File system and workspace watchers for agent triggers**

- How do systems detect "something changed that might need attention"?
- What's the right granularity (file change, git push, CI event, dependency update)?
- How do you avoid alert fatigue / suggestion overload?
- Is there evidence that proactive suggestions improve productivity vs distract?

Search: "AI agent file watcher trigger pattern", "proactive AI assistant
productivity evidence", "agent ambient monitoring alert fatigue", "developer
tool proactive notification research"

**Q1.3: Proactive knowledge gap detection beyond scheduled sweeps**

- Do any systems detect knowledge gaps in real-time during task execution
  (not just on a maintenance timer)?
- How does the "just-in-time research" pattern work in practice?
- What triggers are most valuable (test failures, import errors, API calls
  to unknown endpoints)?

Search: "just-in-time knowledge retrieval AI agent", "real-time knowledge
gap detection coding agent", "reactive knowledge acquisition trigger patterns"

---

## Dimension 2: Cross-Session and Cross-Workspace Learning

FormicOS knowledge is workspace-scoped. Workspace A's lessons are invisible
to Workspace B. There is no persistent operator profile across sessions.

### What to search for

**Q2.1: Cross-project knowledge transfer in AI coding systems**

- How do production systems transfer learned patterns between projects?
- Does Cursor/Copilot maintain any cross-repository context?
- How do MCP-based systems share knowledge across workspaces?
- What's the risk model (IP leakage, context pollution, stale transfer)?

Search: "cross-project knowledge transfer AI coding 2025 2026", "Cursor
cross-repository context", "MCP knowledge sharing across workspaces",
"AI agent cross-project learning patterns"

**Q2.2: Persistent user/operator profiles for AI agents**

- How do systems build long-term models of user preferences and working patterns?
- OpenAI's memory system, Claude's memory, Cursor's project-level rules --
  what works and what doesn't?
- What's the right granularity (coding style preferences, architecture
  preferences, domain expertise, communication preferences)?
- How do you handle preference drift over time?

Search: "AI agent persistent user profile 2025 2026", "OpenAI memory system
implementation", "Claude memory architecture", "long-term user modeling AI
assistant", "AGENTS.md operator preferences pattern"

**Q2.3: Federated or hierarchical knowledge architectures**

- How do multi-project systems organize knowledge hierarchy?
  (global knowledge, project knowledge, task knowledge)
- What's the right scoping model to prevent cross-contamination while
  enabling useful transfer?
- How does the "team brain" pattern work (Notion AI, Glean, etc.)?
- Is there evidence from multi-tenant AI systems about knowledge isolation
  vs sharing tradeoffs?

Search: "hierarchical knowledge scoping multi-agent", "team knowledge brain
AI architecture", "federated learning knowledge sharing agent", "multi-tenant
AI knowledge isolation", "knowledge namespace scoping patterns"

---

## Dimension 3: Natural Language Operator Interface

FormicOS has a web UI with structured controls. The Queen accepts
structured task descriptions. There is no conversational "just tell me
what you need" interface for ambient interaction.

### What to search for

**Q3.1: Conversational interfaces for multi-agent orchestration**

- How do Devin, Manus, and Claude Artifacts handle the operator-to-system
  conversational interface?
- Is the "chat with the orchestrator" pattern effective, or do structured
  inputs work better?
- What's the research on natural language task specification vs structured
  forms for coding tasks?
- How do these systems handle ambiguity resolution conversationally?

Search: "conversational interface AI coding agent 2025 2026", "Devin chat
interface design", "Manus operator interaction pattern", "natural language
task specification vs structured input", "conversational task decomposition
AI agent"

**Q3.2: Voice interfaces for developer tools**

- Is anyone successfully using voice as an input modality for AI coding?
- What's the latency/accuracy tradeoff for voice-to-task-specification?
- How do voice interfaces handle code-specific terminology?
- Is this actually a user need, or is it a gimmick?

Search: "voice interface AI coding assistant 2025 2026", "voice-driven
software development", "speech-to-code developer productivity",
"developer voice assistant evidence"

**Q3.3: Progressive disclosure in AI agent interfaces**

- How do systems balance "simple for simple tasks" with "powerful for
  complex tasks"?
- What's the right default: chat-first with structured options available,
  or structured-first with chat available?
- How does Cursor handle the spectrum from "fix this line" to "refactor
  this module"?
- What UX patterns reduce the learning curve for multi-agent systems?

Search: "progressive disclosure AI agent interface", "simple to complex
task interface AI", "Cursor UX design patterns", "multi-agent system
usability research", "AI coding assistant onboarding UX"

---

## Dimension 4: Production Reliability at Scale

FormicOS runs locally on a single node. It has not been tested under
sustained load, multi-user scenarios, or real production failure modes.

### What to search for

**Q4.1: Production deployment patterns for local-first AI agent systems**

- How do Devin, Cursor, and Claude Code handle production reliability?
- What failure modes are most common in long-running agent sessions?
  (context overflow, model API timeout, workspace corruption, event store bloat)
- How do production systems handle model API outages mid-task?
- What's the recovery pattern (retry, checkpoint, replay, abort)?

Search: "AI agent production deployment failure modes 2025 2026", "long-running
agent session reliability", "model API outage recovery agent", "agent checkpoint
and recovery patterns", "Devin reliability engineering"

**Q4.2: Event store scaling and garbage collection**

- How do event-sourced systems handle unbounded event log growth?
- What's the right compaction/snapshotting strategy for agent event stores?
- SQLite WAL performance under sustained write load (millions of events)?
- How do other agent frameworks handle state persistence at scale?

Search: "event sourcing garbage collection compaction patterns", "SQLite WAL
performance millions rows", "agent state persistence scaling", "event store
snapshot strategy", "temporal event sourcing agent systems"

**Q4.3: Multi-user and multi-tenant agent systems**

- How do production agent platforms handle multi-user isolation?
- Is workspace-level isolation sufficient, or do you need process/container
  isolation per user?
- How does Devin handle concurrent users?
- What's the resource model (shared GPU, shared event store, shared knowledge)?

Search: "multi-tenant AI agent platform architecture", "Devin multi-user
architecture", "concurrent AI agent session isolation", "shared GPU multi-agent
resource management"

**Q4.4: Observability and debugging for multi-agent systems**

- What observability patterns work for debugging agent failures?
- How do production systems trace a failure from user request through
  orchestration through individual agent actions?
- What's the right granularity for traces (per-request, per-round, per-tool-call)?
- How do existing OTel integrations for LLM agents actually work in practice?

Search: "multi-agent observability debugging 2025 2026", "LLM agent tracing
OpenTelemetry", "agent failure root cause analysis patterns", "distributed
tracing multi-agent systems", "LangSmith LangFuse agent debugging"

---

## Dimension 5: Meta-Learning (System Improves at Orchestration)

FormicOS's knowledge base accumulates domain knowledge across tasks.
But the system does not improve at orchestration itself -- it doesn't
learn which colony configurations, caste compositions, or strategies
work best for which task types.

### What to search for

**Q5.1: Automated configuration optimization in production agent systems**

- Do any production systems automatically tune their own orchestration parameters?
- How does DSPy's compiler optimization work in practice for multi-agent systems?
- What's the evidence from AgentSquare, Darwin Godel Machine, or STOP for
  automated agent configuration improvement?
- What's the failure rate of automated configuration changes? How often do
  they make things worse?

Search: "automated agent configuration optimization 2025 2026", "DSPy multi-agent
optimization", "Darwin Godel Machine practical results", "agent self-improvement
failure rate", "AgentSquare production deployment"

**Q5.2: Learning which task decomposition strategies work**

- Do any systems learn from past task decompositions to improve future ones?
- How does "configuration memory" work in practice (remember what worked,
  try it again on similar tasks)?
- What's the right representation for "this decomposition strategy worked
  for this class of tasks"?
- How do you measure whether a decomposition was good vs the individual
  agents were good?

Search: "task decomposition learning agent 2025 2026", "orchestration strategy
optimization multi-agent", "configuration memory agent systems", "meta-learning
task planning AI agent", "learning to decompose tasks automatically"

**Q5.3: Colony composition learning (which castes/team shapes work)**

- Is there evidence that dynamically choosing team composition improves
  outcomes vs fixed templates?
- How do systems learn "this task needs 2 coders and no reviewer" vs
  "this task needs 1 coder and 1 researcher"?
- What's the search space and how do you explore it efficiently?
- Is bandit-style exploration (Thompson Sampling over team configurations)
  practical?

Search: "dynamic team composition AI agent 2025 2026", "learning agent team
configuration", "multi-agent team formation optimization", "bandit exploration
agent composition", "adaptive agent role assignment"

**Q5.4: Prompt evolution and automated prompt improvement**

- How do production systems improve their agent prompts over time?
- What's the evidence from EvoPrompt, PromptBreeder, or DSPy optimization?
- Is automated prompt improvement stable, or does it drift/degrade?
- What's the right safety boundary (which prompts can evolve, which are frozen)?

Search: "automated prompt improvement production 2025 2026", "EvoPrompt results
practical", "DSPy prompt optimization stability", "prompt drift agent systems",
"safe prompt evolution boundaries"

---

## Output format

For each dimension, provide:

1. **State of practice** -- what production systems actually do today (not
   what papers propose)
2. **Empirical evidence** -- controlled results where available, practitioner
   reports where not
3. **Implementation patterns** -- concrete architectures, not just concepts
4. **Failure modes and anti-patterns** -- what doesn't work and why
5. **Recommendation for FormicOS** -- specific, actionable, grounded in evidence
6. **Sequencing** -- what to build first, what depends on what

## Priority order for research depth

1. Cross-session/cross-workspace learning (most unique to FormicOS's architecture)
2. Meta-learning / orchestration improvement (highest long-term leverage)
3. Ambient/proactive intelligence (most impactful for "Jarvis" experience)
4. Production reliability (required for any real deployment)
5. Natural language interface (important but most commoditized)

## What NOT to research

- Self-evolution theory/taxonomy (well-covered by Fang et al. and Gao et al.)
- Pheromone routing or stigmergy theory (well-covered)
- Context window management (well-covered)
- LLM selection or model routing (well-covered)
- Benchmark methodology (separate concern)
- Tool design patterns (well-covered via SWE-agent/Aider)
- Basic multi-agent architecture patterns (well-covered)
- Prompt engineering fundamentals (well-covered)

Focus on: **what production systems actually do in 2025-2026, what works,
what fails, and what FormicOS should build next.**
