You are producing a deep research document for FormicOS, a local-first, event-sourced, multi-agent colony framework that coordinates AI agents through stigmergic (pheromone-based) environmental signals rather than direct messaging.

## The thesis to investigate

FormicOS has spent Waves 33-36 building a mature knowledge metabolism system:
- Knowledge entries with Beta(alpha, beta) confidence distributions
- Thompson Sampling for exploration/exploitation at retrieval time
- Gamma-decay with 3 decay classes (ephemeral/stable/permanent)
- Co-occurrence reinforcement with sigmoid normalization
- 6-signal weighted retrieval (semantic/thompson/freshness/status/thread/cooccurrence)
- Proactive intelligence with 7 deterministic rules
- Self-maintenance with 3 autonomy levels
- Knowledge distillation (cluster synthesis)
- Federation with CRDTs for multi-instance knowledge sharing

The hypothesis is: **this solved knowledge system is the missing substrate that makes stigmergic coordination actually work for LLM agents.** Previous stigmergy implementations in AI (MetaGPT's message pool, LangGraph's shared state, CrewAI's memory) lack the confidence modeling, decay dynamics, and exploration/exploitation balance that biological stigmergy requires. FormicOS's knowledge entries -- with their confidence evolution, decay, reinforcement, and proactive maintenance -- are computationally equivalent to pheromone traces with deposition, evaporation, and bounded reinforcement.

## Current FormicOS stigmergy implementation

The system currently has a pheromone-weighted topology for intra-colony agent coordination:
- 5-phase DyTopo loop: Goal, Intent, Route, Execute, Compress
- Cosine similarity routing with threshold tau (default 0.35)
- Pheromone edge weights in [0.1, 2.0]
- Evaporation: w = w * (1 - rho), rho = 0.1
- Reinforcement: w += alpha * reward, alpha = 0.2 (governance-based)
- Clamping: [0.1, 2.0] (equivalent to MMAS tau_min/tau_max)

This operates at the INTRA-colony level (agent-to-agent routing within a single colony).

The knowledge system operates at the INTER-colony level (knowledge entries persist across colonies and workspaces).

The research question is: **how should these two stigmergic layers interact, and what architectural changes would make the combined system more powerful than either layer alone?**

## What the document should cover

### 1. The knowledge-as-pheromone mapping (theoretical grounding)
- Map FormicOS's knowledge system to ACO/stigmergy theory formally
- Knowledge entries = pheromone traces
- Beta confidence = pheromone concentration
- Gamma decay = evaporation
- Thompson Sampling retrieval = probabilistic transition rule
- Co-occurrence = multi-pheromone interaction
- Knowledge distillation = pheromone aggregation/summarization
- How does this compare to Dorigo's standard ACO update? To MMAS? To ACS?
- What does the theory predict about convergence, stagnation, and exploration?
- Cite Dorigo, Stutzle, Gutjahr (convergence proofs), Mavrovouniotis (adaptive evaporation)

### 2. The two-layer stigmergy architecture
- Layer 1 (intra-colony): pheromone-weighted topology, agent-to-agent
- Layer 2 (inter-colony): knowledge entries, colony-to-colony via shared environment
- How should Layer 2 feed back into Layer 1? (e.g., knowledge confidence influencing topology weights)
- How should Layer 1 outcomes feed into Layer 2? (e.g., colony success/failure updating knowledge confidence)
- Are there biological precedents for multi-scale stigmergy? (nest-level vs trail-level in ant colonies)
- Cite Theraulaz & Bonabeau (multi-level construction), Parunak (digital pheromones at multiple scales)

### 3. What the solved knowledge system specifically enables
- Confidence-calibrated retrieval means agents get knowledge proportional to its validated quality (not just recency or similarity)
- Decay means stale knowledge naturally loses influence without manual cleanup
- Thompson Sampling means the system explores uncertain knowledge rather than always exploiting the most confident -- this is the exploration/exploitation balance that ACO requires
- Co-occurrence means related knowledge clusters reinforce each other (multi-pheromone interaction)
- Proactive intelligence means the system detects knowledge degradation before it causes failures (stagnation detection)
- Self-maintenance means the system can spawn corrective colonies when knowledge quality drops (adaptive evaporation)
- What specific failure modes from the ACO literature (stagnation, pheromone saturation, premature convergence) does each feature address?

### 4. Concrete architectural improvements
For each proposal, provide:
- What changes in the codebase (which files, which data structures)
- What the expected improvement is and how to measure it
- What the risks are
- What precedent exists (academic or production)

Candidate improvements to investigate:
- **Knowledge-weighted topology initialization**: When a colony spawns, initialize the DyTopo with edge weights biased by relevant knowledge confidence (high-confidence knowledge about a domain = stronger initial edges between agents working that domain)
- **Colony outcome → knowledge update loop**: Currently ColonyOutcome is replay-derived. Should successful colony outcomes strengthen the knowledge entries that were retrieved during that colony's execution? (This closes the ACO reinforcement loop at the knowledge level)
- **Adaptive evaporation per knowledge domain**: Different domains decay at different rates. Code patterns should be stable (low evaporation). API references should be ephemeral (high evaporation). The decay_class system already enables this -- how should it be tuned based on usage patterns?
- **Stigmergic task routing**: Instead of the Queen explicitly assigning tasks to colony types, could the knowledge environment itself suggest optimal colony configurations? (Knowledge entries tagged with successful colony outcomes create a "pheromone trail" toward effective configurations)
- **Cross-colony trace inheritance**: When a merge edge connects two colonies, should the merged colony inherit pheromone weights from both parent topologies? How does this relate to colony fusion in biological ant systems?
- **Lambda-branching stagnation detection**: The ACO literature's lambda-branching factor measures pheromone distribution breadth. Could an equivalent metric on knowledge confidence distributions detect when the system is converging prematurely?

### 5. What NOT to do (anti-patterns from the literature)
- Why pure stigmergy fails for small teams (< 10 agents) -- cite the density threshold research (Khushiyant 2025, rho_c ~ 0.230)
- Why real-time synchronization is incompatible with trace-based coordination
- Why environment corruption is catastrophic (Di Marzo Serugendo fault taxonomy)
- Why the "simple rules → complex behavior" paradigm doesn't directly transfer to LLM agents (agents are individually complex reasoners)
- What FormicOS's hybrid Queen + stigmergy approach gets right vs. pure emergent systems

### 6. Benchmarking strategy
- How to measure whether stigmergic improvements actually help
- Comparison targets: DyTopo (+6.2 points, 48% token reduction), G-Designer (95% token reduction)
- What tasks benefit most from stigmergic coordination (highly parallelizable, 10+ agents, fault tolerance matters)
- What tasks should NOT use stigmergy (small teams, real-time, global perspective required)
- Specific benchmark suites: HumanEval, MATH, GAIA, SWE-bench

## Research standards

- Cite specific papers with author names, venue, year, and key quantitative findings
- Distinguish between proven results (published benchmarks, production deployments) and theoretical predictions
- When referencing ACO theory, use the standard notation (tau, rho, alpha, beta, eta)
- When proposing architectural changes, reference the actual FormicOS file structure:
  - engine/runner.py (colony execution loop, governance)
  - engine/topology.py (DyTopo, pheromone weights)
  - surface/proactive_intelligence.py (7 insight rules)
  - surface/self_maintenance.py (MaintenanceDispatcher)
  - surface/projections.py (ColonyOutcome, knowledge entries)
  - surface/queen_runtime.py (Queen briefing injection)
  - core/types.py (event types, 55-event union)
- Do NOT propose changes that require new event types without explicitly justifying them
- Do NOT propose changes to the core layer (core/ is the event-sourcing foundation and is stable)
- Prioritize proposals by impact/effort ratio
- Be specific about what can be measured and what the success criteria would be

## What this document is NOT

- Not a tutorial on stigmergy (the audience already knows ACO theory)
- Not a restatement of FormicOS's existing architecture (the audience built it)
- Not a Wave 37 plan (that comes later -- this is the research input)
- Not a theoretical exercise -- every proposal must be implementable in the existing codebase

## Target length

8,000-12,000 words. Dense, cited, actionable. The audience is the architect/developer of FormicOS who will use this document to make concrete decisions about Wave 37+ architecture.
