You are producing a web-researched companion document for FormicOS, a
local-first event-sourced multi-agent colony framework. This document
complements a separate local-only architecture analysis (the "stigmergy
integration prompt") and should NOT duplicate that document's scope.

## What FormicOS already has (do not re-explain these)

- 6-signal weighted retrieval (semantic/thompson/freshness/status/thread/cooccurrence)
- Beta(alpha,beta) confidence with gamma-decay and 3 decay classes
- Thompson Sampling for exploration/exploitation at retrieval
- Co-occurrence reinforcement with sigmoid normalization
- Proactive intelligence (7 deterministic insight rules)
- Self-maintenance with 3 autonomy levels and MaintenanceDispatcher
- Knowledge distillation (HDBSCAN cluster synthesis)
- Federation via Computational CRDTs with Bayesian trust
- Pheromone-weighted topology (DyTopo, 5-phase loop, tau=0.35)
- Colony outcome tracking (replay-derived, surfaced in Wave 36)
- Tiered retrieval with auto-escalation (summary/standard/full)
- Transcript harvest at hook 4.5 using chat_messages
- Inline dedup at extraction (cosine > 0.92)
- Prediction error counters on projection entries

## What FormicOS already learned from NeuroStack

The project deeply analyzed github.com/raphasouthall/neurostack and
integrated these specific patterns:
- Transcript harvest (second extraction pass on full colony transcripts)
- Hebbian co-occurrence reinforcement adapted to result-result pairs
- Merge semantics with provenance union (MemoryEntryMerged event)
- Tiered retrieval thresholds (40-50% resolution at cheap tier)
- Prediction error logging as a staleness signal
- Inline dedup at extraction time
- Gamma decay composition with co-occurrence (separate rates)

Do NOT re-discover or re-explain these patterns. The audience built them.

## What this document should research

### 1. NeuroStack deep dive -- what we missed

Go to https://github.com/raphasouthall/neurostack and study the current
codebase. Specifically investigate:

a) **Memory consolidation patterns**: How does NeuroStack handle long-term
   memory compaction beyond the merge/dedup we already adopted? Are there
   summarization passes, compression hierarchies, or progressive
   abstraction layers that FormicOS doesn't have?

b) **Temporal knowledge graphs**: NeuroStack references a TKG (temporal
   knowledge graph). How is it structured? What are the entity and edge
   schemas? How does it interact with the vector store? FormicOS has a
   basic knowledge graph (KnowledgeEntityCreated/KnowledgeEdgeCreated
   events) but hasn't built temporal dynamics into it.

c) **Session management and context continuity**: How does NeuroStack
   maintain context across sessions? FormicOS is event-sourced and
   rebuilds from replay, but the "what does the agent remember between
   conversations" problem is different from "what can the system
   reconstruct."

d) **Retrieval feedback loops**: Beyond co-occurrence reinforcement (which
   we adopted), does NeuroStack have other retrieval quality signals?
   Click-through analogs, dwell-time equivalents, or implicit relevance
   feedback from downstream task success?

e) **What has changed since we last looked?** NeuroStack is actively
   developed. Check the commit history since March 2026. Are there new
   features, architectural changes, or patterns that post-date our
   integration analysis?

### 2. Multi-agent knowledge systems -- state of the art (March 2026)

Search for the latest research and production systems that address
shared knowledge in multi-agent LLM systems. Specifically:

a) **Mem0 (mem0.ai)**: Current architecture, memory types (semantic,
   episodic, procedural), ADD/UPDATE/DELETE classification, graph memory.
   What has changed in 2025-2026? How do they handle multi-agent shared
   memory? What's their confidence/quality model?

b) **Zep (getzep.com)**: Temporal knowledge graphs for agents. How do
   they handle knowledge decay, contradiction detection, and entity
   resolution? What's their retrieval architecture?

c) **LangMem (LangChain's memory system)**: Current state in 2026.
   Long-term memory, memory types, how it compares to Mem0/Zep.

d) **Cognee**: Knowledge graph construction from unstructured data for
   agents. Architecture, retrieval patterns, quality scoring.

e) **Any new entrants since late 2025** that specifically address
   multi-agent shared knowledge with quality scoring, decay, or
   exploration/exploitation.

For each system, identify:
- What they do that FormicOS doesn't
- What FormicOS does that they don't
- Specific architectural ideas worth stealing
- Published benchmarks or performance claims

### 3. Agent memory benchmarks and evaluation (2025-2026)

Search for published benchmarks specifically evaluating agent memory
systems:

a) What benchmarks exist for long-term agent memory quality?
b) How are retrieval systems for agents evaluated differently from
   standard RAG evaluation?
c) Are there multi-agent memory benchmarks (not just single-agent)?
d) What metrics matter: retrieval accuracy, knowledge freshness,
   contradiction detection rate, knowledge utilization rate?
e) Any benchmarks that specifically test knowledge decay, confidence
   calibration, or exploration/exploitation in retrieval?

FormicOS needs to benchmark against something. Find the right targets.

### 4. Stigmergic coordination empirical evidence (2025-2026)

Search for the LATEST empirical results on multi-agent coordination
patterns. The strategic roadmap document cites a CIO study (March 2026)
showing stigmergic emergence failed 68% of the time. Find:

a) The actual CIO study -- what exactly was tested, what failed, and
   what were the methodology limitations?
b) Any counter-evidence: studies where stigmergic or shared-environment
   coordination outperformed direct messaging or hierarchical delegation
c) The Khushiyant 2025 phase transition paper (arXiv:2512.10166) --
   density threshold rho_c ~ 0.230 where stigmergic coordination
   becomes superior. Get the full details: what was the experimental
   setup, what agents were used, what tasks, and how robust is the
   threshold?
d) Aina and Ha 2025 S-MADRL paper -- virtual pheromone maps with
   curriculum learning scaling to 8 agents. Full methodology and results.
e) Any 2025-2026 papers on blackboard architectures for LLM agents
   (Salemi et al. arXiv:2510.01285 showed 13-57% improvement over
   master-slave). Updated results or follow-ups?
f) DyTopo (dynamic topology generation) -- any follow-up work or
   competing approaches since the original paper?
g) GPTSwarm (ICML 2024) -- has there been follow-up work on learnable
   edge weights between LLM agents?

The goal is to build the empirical evidence base for or against
FormicOS's stigmergic thesis with the most current data available.

### 5. NemoClaw and NVIDIA agent ecosystem -- technical deep dive

The strategic roadmap covered NemoClaw at a business level. This section
needs the TECHNICAL details:

a) Go to https://github.com/NVIDIA/NemoClaw and study the architecture.
   What is the blueprint pattern? How do sandboxed environments work?
   What are the extension points?
b) Study https://github.com/NVIDIA/AgentIQ (NeMo Agent Toolkit). How
   does the YAML configuration system work? What does framework
   integration look like? What would FormicOS need to implement to be a
   supported framework?
c) What is the MCP integration surface in NeMo Agent Toolkit? FormicOS
   already has a FastMCP server with 19 tools. What adaptation is needed?
d) What models does NemoClaw optimize for? Nemotron variants, context
   window sizes, tool-calling capabilities. How do these compare to
   FormicOS's current model support (Anthropic, Gemini, Qwen3 local)?
e) OpenShell runtime -- what security guarantees does it provide? How
   does it compare to FormicOS's code execution sandbox?
f) A2A (Agent-to-Agent) protocol support in the NVIDIA ecosystem. What
   does FormicOS need to implement beyond what it already has?

### 6. Knowledge system patterns from production agent deployments

Search for PRODUCTION deployment reports (not academic papers) from
companies running multi-agent systems with persistent knowledge:

a) How do production systems handle knowledge quality degradation over
   time? What decay models are used in practice?
b) How is contradiction detection handled in production? Are there
   deterministic approaches that work, or is it always LLM-based?
c) What knowledge retention policies do production systems use? How long
   do they keep entries? What triggers cleanup?
d) How do production multi-agent systems handle the "knowledge
   bootstrapping" problem (cold start with empty knowledge base)?
e) Are there production reports on Thompson Sampling or bandit-based
   approaches to knowledge retrieval? (FormicOS may be novel here --
   confirm or deny.)

### 7. Event-sourced agent systems and CRDT-based federation

Search specifically for:

a) Other event-sourced agent frameworks (not just FormicOS). Who else
   uses event sourcing for agent state management? What patterns work?
b) CRDT usage in AI/ML systems. FormicOS uses CRDTs for federated
   knowledge. Are there other systems doing this?
c) The state of agent-to-agent federation in 2026. Beyond FormicOS's
   CRDT-based approach, what other federation patterns exist?
d) Automerge, Yjs, or other CRDT libraries being used in agent systems.

## Research standards

- Cite specific URLs, paper titles, author names, venues, and dates
- Distinguish between peer-reviewed research, industry reports, blog
  posts, and GitHub READMEs
- For each finding, assess: proven (published + replicated), promising
  (published, not replicated), speculative (blog post or single report)
- When citing benchmark numbers, include the benchmark name, dataset,
  and comparison baseline
- Check publication dates -- prioritize 2025-2026 findings over older work
- If a source is behind a paywall or unavailable, note that explicitly
- For GitHub repos, check stars, last commit date, and contributor count
  as quality signals

## What this document is NOT

- Not a re-explanation of FormicOS's architecture (the audience built it)
- Not a re-discovery of NeuroStack patterns already integrated
- Not a business/licensing analysis (a separate document covers that)
- Not a Wave 37 plan (this is research input, not planning output)
- Not an ACO theory primer (the audience knows Dorigo, Stutzle, MMAS)

## Output format

Organize findings by section number. For each finding, include:
- The source (URL, paper citation, or repo reference)
- The key insight
- Relevance to FormicOS (what to steal, what to avoid, what to validate)
- Confidence level (proven/promising/speculative)

Target: 6,000-10,000 words. Dense with citations. Every claim backed by
a specific source. The audience will use this alongside the local-only
stigmergy analysis to make architectural decisions for Wave 37+.
