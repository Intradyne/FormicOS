# Research Prompt: Production Hardening, Benchmark Strategy, and Codebase Maturity for a Multi-Agent AI Colony Framework (2025-2026)

## Context you have

You are a research agent with access to **web search** and **project knowledge** only. You do NOT have access to the FormicOS codebase. Your job is to produce a synthesis document that informs engineering decisions across three upcoming development waves:

- **Wave 40 ("The Refined Colony"):** Codebase health, profiling, integration hardening, documentation truth, frontend consistency. No new features -- pure refinement.
- **Wave 41 ("The Benchmark Colony"):** Aider Polyglot Benchmark adapter engineering, rehearsal infrastructure, colony configuration tuning, pre-submission validation.
- **Wave 42 ("The Proving Colony"):** Public leaderboard submission, ablation study, thesis publication.

## What FormicOS is

FormicOS is an open-source (AGPLv3), local-first, event-sourced, multi-agent AI colony framework. Key architectural features:

- **Stigmergic coordination:** Agents communicate through shared environmental traces (pheromone-weighted topology, Thompson Sampling knowledge retrieval, co-occurrence reinforcement, quality-scored confidence updates with Bayesian decay).
- **Two-layer stigmergy:** Layer 1 is short-term intra-colony pheromone routing (DyTopo adjacency matrix). Layer 2 is long-term inter-colony institutional knowledge (persistent memory entries with confidence posteriors).
- **Queen coordinator:** Plans tasks, delegates to parallel colony groups, manages escalation.
- **Event-sourced substrate:** 58 event types. All truth is replay-derivable. Operator actions (pin/mute/annotate/invalidate) are first-class replayable events.
- **Operator co-authorship:** The operator is a durable co-author of the hive state, not just a viewer. Local editorial actions are retrieval overlays that do NOT mutate shared confidence posteriors.
- **Governance-owned adaptation:** Auto-escalation through routing_override (capability mismatch, governance-owned, replay-visible) is separate from provider fallback (transport/availability, silent, router-owned).
- **Tech stack:** Python 3.12+, Lit Web Components, SQLite WAL, Qdrant, FastMCP, Starlette.
- **Test suite:** 2,100+ tests across 153 test files. Layer boundary lint. CI with ruff, pyright, pytest.

The product thesis: **FormicOS is an editable shared brain with operator-visible traces, where every decision is inspectable, every assumption is editable, and every adaptation is reversible.**

## What to research

Search the project knowledge FIRST for every section. It contains extensive prior research on stigmergy, multi-agent coordination, benchmarking, and the FormicOS architecture. Use web search to fill gaps and find current (2025-2026) developments.

---

### Section 1: Python Codebase Refactoring Patterns for Large AI Systems (Wave 40)

**Goal:** Inform the refactoring of 5 high-traffic files (1,500-2,300 lines each) that have grown through 7 waves of additive development by different teams.

Research:

1. **Large-file decomposition patterns in Python.** What are the best practices for splitting a 2,000-line module that mixes governance logic, tool dispatch, convergence computation, and round execution? Registry patterns vs strategy patterns vs simple module extraction with re-exports. When does splitting help navigability and when does it just scatter logic?

2. **Error handling boundary patterns for multi-layer systems.** FormicOS has three error boundaries: HTTP/route surfaces, UI-facing API responses, and internal tool-return paths. The structured error system exists but adoption is inconsistent. What patterns do production Python systems use to enforce consistent error contracts at boundary crossings without forcing every internal function into HTTP error shapes?

3. **Event-sourced system profiling techniques.** How do production event-sourced systems profile and optimize projection rebuilds, event handler chains, and read-model assembly? What are the known bottleneck patterns (O(events) replay, O(rules x entries) rule evaluation, retrieval latency under Thompson Sampling stochasticity)?

4. **Cross-feature integration testing strategies for AI agent systems.** With 58 event types, operator overlays, federation, tiered retrieval, governance escalation, and earned autonomy interacting, what testing patterns catch interaction bugs that single-feature tests miss? Property-based testing? Scenario matrices? Chaos testing for agent systems?

5. **Frontend component decomposition in Lit/Web Components.** When a Lit component reaches 1,000 lines (colony-detail, knowledge-browser), what are the proven decomposition patterns? Sub-components vs mixins vs controllers? How do production Lit apps manage state across decomposed components without prop-drilling?

---

### Section 2: Aider Polyglot Benchmark Strategy (Wave 41)

**Goal:** Inform the engineering of a FormicOS adapter for the Aider Polyglot Benchmark and the design of rehearsal infrastructure.

Research:

1. **Aider Polyglot Benchmark: current state, format, and scoring.** What is the exact task format (git repo + instruction + target files)? What edit formats does Aider accept (search/replace blocks, whole-file rewrites)? How is scoring done (test suite pass/fail per task)? What is the current leaderboard state as of 2025-2026? What scores do Claude Sonnet, GPT-4o, and fine-tuned models achieve? What did PewDiePie's fine-tuned model actually achieve and with what setup?

2. **Multi-agent approaches to coding benchmarks.** Has anyone submitted a multi-agent system to the Aider leaderboard or similar coding benchmarks (SWE-bench, HumanEval, MBPP, LiveCodeBench)? What coordination patterns did they use? What were the results compared to single-agent baselines? What are the known failure modes of multi-agent approaches on code editing tasks?

3. **Multi-file completion detection.** The Polyglot benchmark includes multi-file, multi-language edits. How do existing tools (Aider, Cursor, Devin, SWE-Agent, OpenHands) detect when a multi-file edit is complete and consistent? What validation strategies do they use?

4. **Knowledge accumulation across sequential benchmark tasks.** The stigmergic thesis predicts that colony performance should improve as knowledge accumulates across tasks. Has anyone measured this effect in coding benchmarks? Are there published results showing learning curves across sequential code editing tasks? What knowledge extraction strategies help vs hurt for code-editing contexts?

5. **Cost-performance optimization for benchmark runs.** Running 225 tasks through a multi-agent colony is expensive. What strategies do benchmark participants use to optimize cost (model routing, early stopping, retrieval caching, tiered model selection)? What is the typical cost per task for competitive benchmark entries?

---

### Section 3: Ablation Study Design and Publication Strategy (Wave 42)

**Goal:** Inform the design of a credible ablation study and the publication of results.

Research:

1. **Ablation study design for multi-agent systems.** What are the standard ablation configurations for proving a multi-agent coordination thesis? What baselines are expected (single-agent, multi-agent without coordination, multi-agent with partial coordination)? How many configurations are credible without being excessive? What statistical methods handle the variance inherent in LLM-based systems?

2. **The McEntire 68% failure finding.** Search project knowledge for the McEntire study on stigmergic multi-agent coordination that found 68% failure rates. What exactly did that study test? What was the agent architecture? How does it differ from FormicOS's purpose-built stigmergic infrastructure? What would a credible rebuttal look like?

3. **Publishing AI benchmark results: norms and credibility.** What makes an AI benchmark result credible vs dismissible? Reproducibility requirements? Variance reporting? Cherry-picking concerns? How do serious benchmark publications handle negative or mixed results? What's the difference between a blog post, an arXiv preprint, and a peer-reviewed submission in terms of credibility?

4. **The "coordination vs capability" narrative.** FormicOS's thesis is that coordination architecture compensates for individual model capability -- several cheaper models sharing a rich knowledge substrate can match or beat a single expensive model. Has this thesis been tested elsewhere? What results exist? What are the strongest counterarguments?

5. **Leaderboard submission mechanics.** How does the Aider Polyglot leaderboard actually work? Is it self-reported? Is there a verification process? What metadata is required? Can a multi-agent system entry be distinguished from a single-model entry on the leaderboard?

---

### Section 4: Production AI Agent System Maturity (Cross-Wave)

**Goal:** Inform the broader maturity posture of a framework preparing for public scrutiny.

Research:

1. **What do production multi-agent frameworks look like in 2025-2026?** Compare FormicOS's architecture (event-sourced, stigmergic, operator-supervisable, local-first) against the current state of CrewAI, AutoGen, LangGraph, OpenHands, Devin, and any other frameworks that have shipped real products. Where is FormicOS genuinely differentiated? Where is it behind? What capabilities do enterprise buyers expect?

2. **Operator trust and supervisability patterns.** FormicOS's Wave 39 added operator co-authorship (pin/mute/annotate/invalidate as replayable events, local-first editorial overlays, earned autonomy recommendations). How does this compare to operator control surfaces in other agent frameworks? What patterns have enterprise deployments found necessary for trust? What's missing?

3. **The NeuroStack / NVIDIA agent ecosystem.** Search project knowledge for NemoClaw, NeuroStack, and NVIDIA integration research. What is the current state of the NVIDIA agent toolkit ecosystem? How do open-source frameworks integrate with it? What are the licensing and compatibility considerations?

4. **AGPLv3 dual-licensing strategy for AI frameworks.** Search project knowledge for the financial/licensing navigation guide. What are the current best practices for AGPLv3 open-source projects that want to offer commercial licensing? How do Grafana, Odoo, and other AGPLv3 projects structure their dual-license programs? What are the CLA requirements?

5. **Documentation standards for open-source AI frameworks.** What documentation do serious open-source AI projects provide? Architecture guides? Operator manuals? API references? Contribution guides? What's the minimum documentation set that makes an AI framework credible for external adoption? Compare against what FormicOS has (CLAUDE.md, OPERATORS_GUIDE.md, KNOWLEDGE_LIFECYCLE.md, AGENTS.md, 49 ADRs, CONTRIBUTING.md, SECURITY.md, GOVERNANCE.md).

---

## Output format

Produce a single synthesis document with these sections:

1. **Executive Summary** (1 page): The 5 most important findings that should influence Wave 40-42 decisions.

2. **Wave 40 Findings** (Section 1 research): Concrete recommendations for refactoring, profiling, testing, and documentation with evidence from comparable projects.

3. **Wave 41 Findings** (Section 2 research): Benchmark format details, multi-agent benchmark precedents, adapter design considerations, and cost/performance data.

4. **Wave 42 Findings** (Section 3 research): Ablation design recommendations, publication strategy, and narrative positioning.

5. **Maturity Assessment** (Section 4 research): Where FormicOS stands relative to the field, where it's genuinely differentiated, and what gaps matter most for credibility.

6. **Open Questions**: Anything the research couldn't resolve that the engineering team should investigate directly.

## Research principles

- Search project knowledge FIRST for every topic. It contains extensive prior research that should be the foundation.
- Use web search to fill gaps and find developments after the project knowledge was written.
- Cite sources. Distinguish between project-knowledge findings and web-search findings.
- Be honest about what you couldn't find. "No published results exist for X" is a valid and useful finding.
- Prefer concrete data (benchmark scores, cost figures, adoption numbers) over general commentary.
- When findings conflict, present both sides with evidence rather than picking a winner.
- Do not fabricate benchmark numbers, framework comparisons, or citations. If you can't verify a claim, say so.
