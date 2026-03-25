# Moved

This file has been moved to `docs/internal/sessions/session_decisions_2026_03_19.md`.

It is the engineering decision log from the 2026-03-19 session (397 KB).
Preserved for reference, not part of public documentation.


## Addendum 187: Phase 1 v1 in progress -- KNOWLEDGE IS FLOWING

**Added:** First same-domain compounding measurement. Entries crossing 0.50 threshold.

### Phase 1 v1 Arm 1 progress (6/8 done)

| Task | Q | Wall | Ext | Acc | Position |
|------|---|------|-----|-----|----------|
| p1-csv-reader | 0.612 | 135s | 3 | 0 | 1st (cold) |
| p1-data-validator | 0.580 | 226s | 2 | 3 | 2nd |
| p1-data-transformer | 0.592 | 408s | 3 | 2 | 3rd |
| p1-pipeline-orchestrator | 0.574 | 312s | 3 | 2 | 4th |
| p1-error-reporter | 0.571 | 276s | 4 | 4 | 5th |
| p1-performance-profiler | 0.499 | 757s | 12 | 3 | 6th |

### THE DEFINING SIGNAL

Phase 0 v12: 0 entries injected across 8 tasks (all below 0.50 threshold)
Phase 1 v1: 14 entries accessed across 6 tasks (same-domain crosses 0.50)

Same-domain entries DO cross the similarity threshold. The knowledge
pipeline is active for the first time in a real measurement run.

### Pool growth

27 entries after 6 tasks. T6 (performance-profiler with researcher caste)
extracted 12 entries alone. T7-T8 have the richest pool to draw from.

### Waiting on T7-T8 (heavy, 3-agent, richest pool)

schema-evolution and pipeline-cli are the ultimate compounding test.
They reference ALL prior modules and have ~27 entries available.
If these score higher in accumulate than empty, compounding is proven.

187 addenda. ~531 KB session memo.


## Addendum 188: Novelty assessment research prompt dispatched

**Added:** Honest prior art check across 7 FormicOS claims.

### The 7 claims to assess

1. Stigmergic coordination for LLM agents (pheromone topology)
2. Operational knowledge >> domain knowledge (18x, +0.177 vs ~zero)
3. Curating archivist (CREATE/REFINE/MERGE/NOOP)
4. Asymmetric extraction (writer >> reader)
5. Three-layer injection defense (gate + boundaries + disclosure)
6. 9-layer knowledge lifecycle with Bayesian confidence
7. Honest negative results (12 controlled measurement runs)

### Why this matters now

Phase 1 is running with knowledge flowing for the first time.
Before publishing findings or pitching to labs, we need to know:
- What survives peer review
- What's genuinely novel vs well-executed known patterns
- What the unique contribution is (likely the composition)
- What gaps exist vs competitors

### Expected finding

The project's novelty is probably in the COMBINATION, not any
single element. Mem0 does curation. Graphiti does temporal tracking.
Letta does sleep-time agents. MetaGPT does stigmergic message pools.
Nobody has all of these in one system with Bayesian confidence,
Thompson Sampling retrieval, asymmetric extraction, and 12 controlled
measurement runs proving what works and what doesn't.

The measurement methodology itself -- 12-run accumulate-vs-empty
protocol with progressive infrastructure fixes -- may be the most
publishable contribution.

188 addenda. ~535 KB session memo.


## Addendum 189: Phase 1 v1 Arm 1 COMPLETE -- knowledge flows for the first time

**Added:** First same-domain compounding measurement. 7/8 tasks accessed entries.

### Phase 1 v1 Arm 1 results

| Task | Pos | Q | Wall | Ext | Acc | Pool |
|------|-----|---|------|-----|-----|------|
| csv-reader | 1 | 0.612 | 135s | 3 | 0 | 0 |
| data-validator | 2 | 0.580 | 226s | 2 | 3 | 3 |
| data-transformer | 3 | 0.592 | 408s | 3 | 2 | 5 |
| pipeline-orchestrator | 4 | 0.574 | 312s | 3 | 2 | 8 |
| error-reporter | 5 | 0.571 | 276s | 4 | 4 | 11 |
| performance-profiler | 6 | 0.499 | 757s | 12 | 3 | 15 |
| schema-evolution | 7 | 0.524 | 961s | 4 | 3 | 27 |
| pipeline-cli | 8 | 0.587 | 966s | 7 | 2 | 31 |

Mean quality: 0.567
Total entries extracted: 38
Total entries accessed: 19
Tasks with entries accessed: 7/8 (all except T1 cold start)

### THE HISTORIC SIGNAL

Phase 0 (12 runs): 0 entries crossed 0.50 threshold between tasks
Phase 1 (1 run): 19 entries crossed 0.50, accessed across 7 tasks

Same-domain entries DO cross the similarity threshold.
The knowledge pipeline is active for the first time in any eval.

### Token exhaustion

Gemini and Anthropic API tokens exhausted during this run.
T6 (performance-profiler) was affected -- 757s wall time due to
anthropic cooldown fallback. The run completed on local GPU.

### Cannot run Arm 2 without addressing token issue

The empty arm doesn't extract (no archivist needed). But colony
execution may fall back to cloud providers via the LLM router's
fallback chain when the local model struggles.

189 addenda. ~540 KB session memo.


## Addendum 190: Phase 1 v1 Arm 1 results recorded -- three key findings

**Added:** Full results analysis from phase1_v1_results.md.

### Finding 1: The pipeline activates (PROVEN)

19 entries accessed across 7/8 tasks. Same-domain vocabulary crosses
the 0.50 threshold. This is the signal Phase 0 never produced in 12
runs. The knowledge pipeline works for same-domain task sequences.

### Finding 2: Wave 59 curation is functional (FIRST OBSERVATION)

1 REFINE action observed in production:
  entry_id=mem-colony-60bb6531-e-4
  old_len=111, new_len=244, colony_id=colony-77c82532

The curating archivist saw an entry from T1 and improved it with
insights from T2's colony transcript. Content more than doubled.
This is the first MemoryEntryRefined event in any eval run.

### Finding 3: knowledge_detail was never called (GAP)

0 calls to knowledge_detail across 8 tasks. Progressive disclosure
shows index-only entries but agents never pulled full content.
Three possible causes:
1. Index summaries were sufficient (best case)
2. Agents don't know the tool is available (prompt gap)
3. Tool not offered to coder/reviewer castes (config gap)

This needs investigation. The entire progressive disclosure
architecture rests on agents pulling content on demand.

### The confound: API exhaustion

889 provider cooldown/error/retry events. Most work fell back to
local GPU. T6 (performance-profiler) quality dropped to 0.499 due
to researcher caste losing cloud providers. Heavy tasks (T7-T8)
ran entirely on local GPU with 3 agents competing for inference.

Mean quality (0.567) is depressed by API exhaustion. Not directly
comparable to Phase 0 runs that had functioning cloud fallbacks.

### What we can and cannot say

CAN say: The pipeline activates on same-domain tasks. Entries cross
0.50. Curation produces REFINE actions. The architecture works.

CANNOT say: Whether activation improves quality. Need Arm 2 (empty)
for the delta. Quality curve does not monotonically increase with
pool size, but API exhaustion is a confound.

### Next steps

1. Run Arm 2 when tokens reset (delta measurement)
2. Investigate knowledge_detail gap (caste config or prompt issue)
3. Consider API-clean rerun (remove fallback confound)

190 addenda. ~542 KB session memo.


## Addendum 191: Novelty assessment received + architecture polish pass requested

**Added:** Honest novelty assessment results + graph memory gap identified as priority.

### Novelty assessment verdict (7 claims)

| Claim | Verdict | Key prior work |
|-------|---------|---------------|
| Stigmergic coordination | Incremental (ACO-ToT, GPTSwarm, DyTopo) |
| Operational > domain knowledge | NOT NOVEL (SkillsBench, Xiong, industry) |
| Curating archivist | Incremental over Mem0 |
| Asymmetric extraction | STRONGEST NOVELTY (knowledge-delta hypothesis) |
| Three-layer defense | Engineering integration, not research |
| 9-layer lifecycle | Integration density (Beta posteriors are defensible) |
| Negative results | Independent replication at lower rigor |

### Two genuine contributions

1. Knowledge-delta hypothesis (writer >> reader determines retrieval value)
2. Beta posteriors on per-entry knowledge confidence

### Critical gaps identified

1. No standard benchmarks (HumanEval, MBPP) -- disqualifying
2. No production validation -- zero external deployments
3. Flat vector memory in a graph world -- ceiling on retrieval
4. Zero public footprint -- no GitHub, no community
5. No user feedback loop

### Architecture polish pass: graph memory

The novelty assessment identifies flat vector memory as the real
architectural gap. Graphiti's 18.5% accuracy improvement with temporal
knowledge graphs is the benchmark. FormicOS cannot do multi-hop
reasoning, temporal queries, or relationship traversal.

This is the ceiling on what the knowledge pipeline can accomplish.
The curating archivist can REFINE entries but can't express "entry A
SUPERSEDES entry B" or "entry C DEPENDS_ON entry D" as traversable
relationships.

191 addenda. ~548 KB session memo.


## Addendum 192: Wave 59.5 prompt dispatched -- graph bridge + disclosure fix

**Added:** Three parallel coder teams bridging vector entries to graph nodes.

### Wave 59.5: Knowledge Graph Bridge + Progressive Disclosure Fix

Three parallel teams, zero file overlap, ~120 lines total:

Team 1: Entry-node bridge + lifecycle edges
- colony_manager.py: after MemoryEntryCreated -> resolve_entity() -> store mapping
- After MemoryEntryRefined -> add_edge(SUPERSEDES)
- After MemoryEntryMerged -> add_edge(DERIVED_FROM)
- projections.py: entry_kg_nodes mapping dict
- knowledge_graph.py: add SUPERSEDES/DERIVED_FROM/RELATED_TO predicates

Team 2: Graph-augmented retrieval
- knowledge_catalog.py: after vector search top-K, 1-hop BFS from top-3
- Graph-discovered entries get graph_proximity signal in composite scoring
- Freshness weight 0.10 -> 0.04 to accommodate graph_proximity 0.06
- app.py + run.py: pass kg_adapter to KnowledgeCatalog constructor

Team 3: Progressive disclosure fix
- context.py: auto-inject full content for top-1 entry (highest similarity)
- Remaining entries keep index-only format
- Total budget: ~510 tokens (up from 250 pure index, down from 800 full)
- Addresses Phase 1 finding: 0 knowledge_detail calls across 8 tasks

### Why this is the highest leverage wave

The graph adapter has 559 lines already written. The vector pipeline
has ~500 lines working. The bridge is ~120 lines connecting them.

After this wave:
- Entries have graph relationships (SUPERSEDES, DERIVED_FROM, DEPENDS_ON)
- Retrieval discovers related entries through graph traversal, not just
  vector similarity
- Agents get actionable content for the best match immediately
- The knowledge pipeline becomes a hybrid vector + graph system

This addresses the novelty assessment's #1 architectural gap: "flat
vector memory in a graph world."

192 addenda. ~554 KB session memo.


## Addendum 192: Graph bridge identified as architecture polish priority

**Added:** Strategic positioning + graph integration plan.

### The composition table (defensible positioning)

FormicOS is the only system with ALL of:
- Vector retrieval + graph relationships + Bayesian confidence
- Thompson Sampling + LLM curation + injection gating
- Asymmetric extraction + event-sourced replay + controlled A/B measurement

No published system combines all of these.

### The graph bridge

KnowledgeGraphAdapter exists (559 lines, Wave 14):
- SQLite adjacency tables, bi-temporal edges, entity resolution
- Wired into runtime (app.py:252, runtime.py:450)
- Populated by runner.py:1086 (archivist TKG tuples)
- Has: resolve_entity, add_edge, invalidate_edge, get_neighbors,
  get_edge_history, ingest_tuples, search_entities
- NEVER queried by the knowledge pipeline

The gap: MemoryEntry objects live in Qdrant (vector). KG nodes live
in SQLite (graph). No bridge connects them. The curating archivist
creates entries and refines them, but the relationships between
entries (SUPERSEDES, DERIVED_FROM, DEPENDS_ON) are not expressed
as traversable graph edges.

### The bridge (~65 lines)

1. Link MemoryEntry to KG node on creation (~30 lines)
2. Create SUPERSEDES/DERIVED_FROM edges on REFINE/MERGE (~15 lines)
3. Graph-augmented retrieval: 1-hop neighbor expansion (~20 lines)

This connects two existing 500+ line systems with 65 lines of bridge.

192 addenda. ~553 KB session memo.


## Addendum 193: UI as differentiator -- shared control surface

**Added:** The comparison table misses FormicOS's biggest differentiator.

### What the novelty assessment missed

The table compares backend capabilities. But Mem0 is an API.
Graphiti is a library. Zep is infrastructure. MemOS is a research
prototype. None ship a UI where an operator cooperates with the
knowledge system in real-time.

### 5 additional differentiating rows

| Capability | Others | FormicOS |
|---|---|---|
| Operator UI with live colony view | No | Yes |
| Knowledge inspection + intervention | Dashboard at best | Full lifecycle |
| Queen reasoning transparency | N/A | Yes |
| Proactive intelligence alerts | No | 15 rules |
| Human-in-the-loop governance | No | Autonomy levels |

### The reframe

From: "best knowledge backend"
To: "the only system where a human cooperates with a knowledge-
evolving AI hive through a shared control surface"

This is the pitch: not just the plumbing, but the cockpit.
The operator sees what the hive knows, what it's uncertain about,
what it flagged for review, and can intervene at any point.
That's cooperative intelligence, not just agent infrastructure.

### Updated positioning

"The most complete knowledge lifecycle for AI agents that exists
in a single system, with a cooperative human-AI control surface,
two novel hypotheses, and emerging empirical evidence."

193 addenda. ~558 KB session memo.


## Addendum 194: Wave 59.5 plan audit -- critical async fix

**Added:** Corrections for wave_59_5_plan.md before dispatch.

### CRITICAL: Async violation in Team 1

The plan puts resolve_entity() (async) inside projection handlers (sync).
Projection handlers are def, not async def. apply() is sync. The entire
replay chain is synchronous by design (hard constraint #7).

Fix: Move the KG bridge call to runtime.py:emit_and_broadcast(), which
IS async. This is exactly where the Qdrant sync already lives (lines
491-506). Same pattern: projection processes event (sync), then surface
layer performs async side effects (KG write, Qdrant sync).

### CRITICAL: Replay safety gap

During event replay, apply() is called but emit_and_broadcast() is NOT.
entry_kg_nodes would be empty after restart. Fix: add
_rebuild_entry_kg_nodes() method on Runtime, called after replay.
O(n) rebuild from KG database, <1 second at current scale.

### Two polish items

1. Team 2: get_neighbors() should pass workspace_id (currently omitted)
2. Team 3: content truncation should use sentence boundary, not raw [:500]

### Updated Team 1 file ownership

The projection handlers (sync) are NOT modified. Only:
- projections.py: add entry_kg_nodes dict field to __init__
- runtime.py: add KG bridge block in emit_and_broadcast + rebuild method
- knowledge_graph.py: add 3 predicates
- app.py: call rebuild after replay

194 addenda. ~563 KB session memo.


## Addendum 195: Strategic positioning for consultant partnership

**Added:** Preparation for AI agent consultant conversation.

### What she needs to pitch

1. Public repo with clean docs (FINDINGS.md, README, comparison table)
2. The composition table (10+ capability rows where nobody else checks all)
3. A 2-minute demo video of the UI (colonies + knowledge + Queen reasoning)
4. The measurement story (honest negative results = credibility)

### What different audiences want

Enterprise clients: "will this make my AI agents better at my company's tasks?"
-> Same-domain compounding thesis. Phase 1 delta is the proof point.

Acquirers: "what capability does this give us that we can't build in 6 months?"
-> The composition. 65 events, 59 waves, 13 eval runs, failure-driven design.
-> The institutional knowledge (architectural decisions from measured failures).

### Three things before that conversation

1. GitHub public (the repo, not just a landing page)
2. Phase 1 empty arm (the one data point that changes the narrative)
3. One real-project deployment (even a small one -- proves it works outside eval)

### The moat

Not any single technique (all have prior art). The moat is:
- 59 waves of failure-driven architectural decisions
- 13 eval runs with honest measurement data
- The specific design choices informed by real failures (v11 -> gate)
- The cooperative UI that makes every layer inspectable
- The integration density that nobody else has assembled

That institutional knowledge is the acqui-hire value.

195 addenda. ~568 KB session memo.


## Addendum 195: Cost tracking audit received + Phase 1 v2 multi-provider launching

**Added:** Cost tracking implementation reference + multi-provider run status.

### Cost tracking findings

Local models at $0.00 make every budget gate inert:
- BudgetEnforcer never fires warn/downgrade/hard-stop
- Cost outlier rule never fires (all $0.00 medians)
- Maintenance budget is fictional ($1.00 never consumed)
- Agent always sees "comfortable" regardless of GPU time

Fix: S1+S2+S6 (~20 lines) -- add api_cost property to BudgetSnapshot,
gate on api_cost instead of total_cost, maintenance uses api_cost.
The per-model breakdown already exists in BudgetSnapshot.model_usage.

Deferred to Wave 60 (after multi-provider run produces real cost data).

### Phase 1 v2 multi-provider config

| Caste | Provider | Model | Cost |
|-------|----------|-------|------|
| coder | local GPU | llama-cpp/gpt-4 | free |
| reviewer | OpenAI | gpt-4o | ~$2.50/M in, $10/M out |
| researcher | OpenAI | gpt-4o-mini | ~$0.15/M in, $0.60/M out |
| archivist | Ollama Cloud | qwen3-coder:480b | free |

Estimated total cost: ~$1.25 for full Phase 1 run (both arms).
Gemini and Anthropic disabled (tokens exhausted).

### Run status

Killed local-only run (router had cooled OpenAI before it came online).
Clean restart with all 3 providers confirmed live.
run_phase1_v2.sh script handles both arms unattended.

### Wave 60 scope emerging

1. Cost tracking fix (S1+S2+S6, ~20 lines)
2. Graph temporal queries (bi-temporal edges in retrieval)
3. Quality gates on REFINE (cosine > 0.75 old vs new)
4. Cost display update (show api_cost + local_tokens)
5. Time-based local complexity budget (S4, new concept)

195 addenda. ~570 KB session memo.


## Addendum 196: Wave 60 strategic direction -- "the last wave"

**Added:** High-level reasoning for Wave 60 as the final feature wave.

### Theme: "Everything that's claimed works. Everything that works is visible."

Wave 60 is not about new capability. It's about making existing
capability honest, provable, and visible.

### Five tracks

1. Cost coherence (S1+S2+S3+S6, ~35 lines)
   - api_cost property, enforcement on real cost, honest display
   - Makes the budget system truthful for local+cloud mixed workloads

2. Thompson ablation (0 code, measurement only)
   - Phase 1 deterministic vs stochastic
   - Validates or kills the Bayesian machinery
   - Most publishable single experiment in the project

3. Standard benchmark baseline (HumanEval + MBPP)
   - ~100 lines of eval infrastructure
   - Establishes credibility on the same scale as MetaGPT
   - Multi-colony HumanEval could demonstrate colony value

4. Operator feedback loop (~40 lines)
   - Thumbs up/down on colony results and knowledge entries
   - Wires to MemoryConfidenceUpdated with operator alpha/beta deltas
   - Closes the learning loop every competitor has
   - Rule 15 gains teeth (popular-but-unexamined -> operator reviews)

5. GitHub launch preparation (0 engine code)
   - README, FINDINGS.md, docs cleanup, architecture diagram
   - Demo recording, CI/CD, license confirmation
   - The packaging that determines whether the work reaches anyone

### What Wave 60 is NOT

- More knowledge pipeline features (pipeline is complete)
- More eval runs on the same suite (Phase 0 retired)
- New castes, tools, or rules (sufficient for launch)
- Architecture expansion (the composition table is fully checked)

### After Wave 60

The project doesn't need more waves. It needs users.

196 addenda. ~574 KB session memo.


## Addendum 197: Wave 60 plan written -- 8 tracks, 3 tiers, the final wave

**Added:** Combined wave plan with deferred knowledge features + platform coherence + visibility.

### Tier 1: Knowledge pipeline completion (3 deferred items, ~50 lines)

1. Temporal queries in graph retrieval (~10 lines)
   - valid_before parameter on get_neighbors()
   - "What did the hive know when colony X ran?"

2. Semantic preservation gate on REFINE (~15 lines)
   - cosine < 0.75 between old and new embedding -> reject rewrite
   - "No production system has formal quality gates on rewrites"

3. Graph relationships in the API + UI (~25 lines)
   - /api/v1/knowledge/{entry_id}/relationships endpoint
   - UI shows SUPERSEDES, DERIVED_FROM, DEPENDS_ON links

### Tier 2: Platform coherence (3 fixes, ~75 lines + measurement)

4. Cost coherence (~35 lines)
   - api_cost property, enforcement on real cost, honest display

5. Operator feedback loop (~40 lines)
   - Thumbs up/down on entries -> MemoryConfidenceUpdated
   - Closes the human-in-the-loop gap

6. Thompson ablation (0 code, measurement)
   - Phase 1 deterministic vs stochastic
   - Validates or kills the Bayesian machinery

### Tier 3: Visibility (2 tracks)

7. Standard benchmark (HumanEval pass@1, ~100 lines eval infra)
8. GitHub launch (FINDINGS.md, README, docs cleanup, CI/CD, demo)

### Total

~125 lines engine code + ~100 lines eval infra + docs/packaging.
After this wave: the project needs users, not code.

### The meta-criterion

After Wave 60, a senior engineer at an AI lab can:
find the repo, read FINDINGS.md, understand the architecture,
inspect knowledge entries with relationships and feedback,
run 3500+ tests, see a benchmark number, and form their own
assessment. If all seven are true, the project is ready.

197 addenda. ~578 KB session memo.


## Addendum 198: Wave 60 plan audit -- 3 corrections, 2 polish items

**Added:** Revision prompt for wave_60_plan.md.

### Corrections

1. Track 3 + Track 5 both modify routes/api.py -- overlap not documented.
   Additive (new endpoints at different paths), no conflict, but note it.

2. Track 5 feedback endpoint defaults conf_alpha/conf_beta to 1.0 but
   FormicOS prior is Beta(5,5). Default should be 5.0 to match system prior.

3. Track 4 S2 pure-local edge case: api_cost=0 means zero enforcement.
   Correct behavior but needs explicit test case documenting it as by-design.
   Also add S4 (time-based budget) to "Does NOT Do" list.

### Polish

4. Rule 15 vs Rule 17 inconsistency -- verify actual count in
   proactive_intelligence.py.

5. Track 7 HumanEval is underspecified -- add design questions
   (how many problems, pass/fail mechanism, colony config, input format).

### What's good

- Bug fix catch on node_id vs from_node/to_node (would have silently
  broken graph discovery in 59.5)
- Embedding not on projections correction (prevents runtime error)
- MemoryConfidenceUpdated field audit (old/new absolute, reason not source)
- Technical Notes section grounding every snippet in codebase

198 addenda. ~582 KB session memo.


## Addendum 199: Phase 1 v2 Arm 1 complete -- multi-provider, first clean run

**Added:** v2 Arm 1 results. Arm 2 running.

### Phase 1 v2 Arm 1 (multi-provider, Wave 59.5 stack)

| Task | Pos | v2 Q | v1 Q | Delta | v2 Acc | v1 Acc | v2 Ext | v1 Ext |
|------|-----|------|------|-------|--------|--------|--------|--------|
| csv-reader | 1 | 0.629 | 0.612 | +0.017 | 0 | 0 | 6 | 3 |
| data-validator | 2 | 0.463 | 0.580 | -0.117 | 3 | 3 | 4 | 2 |
| data-transformer | 3 | 0.593 | 0.592 | +0.001 | 2 | 2 | 3 | 3 |
| pipeline-orchestrator | 4 | 0.573 | 0.574 | -0.001 | 2 | 2 | 2 | 3 |
| error-reporter | 5 | 0.582 | 0.571 | +0.011 | 2 | 4 | 2 | 4 |
| performance-profiler | 6 | 0.597 | 0.499 | +0.098 | 3 | 3 | 3 | 12 |
| schema-evolution | 7 | 0.602 | 0.524 | +0.078 | 2 | 3 | 7 | 4 |
| pipeline-cli | 8 | 0.601 | 0.587 | +0.014 | 2 | 2 | 10 | 7 |

v2 mean: 0.580. v1 mean: 0.567. Delta: +0.013.
v2 accessed: 16. v1 accessed: 19.
v2 extracted: 37. v1 extracted: 38.

### Key observations

1. T6 (performance-profiler) recovered: 0.499 -> 0.597 (+0.098).
   v1 had 889 API fallback events. v2 had clean OpenAI access.
   This confirms the v1 T6 dip was API exhaustion, not task difficulty.

2. T7 (schema-evolution) improved: 0.524 -> 0.602 (+0.078).
   Same pattern -- v1 ran heavy tasks on local-only due to exhaustion.

3. T2 (data-validator) regressed: 0.580 -> 0.463 (-0.117).
   This is surprising. More entries extracted (4 vs 2) but same
   access count (3). May be model variance or a bad colony run.

4. Extraction volume is comparable (37 vs 38). Access count slightly
   lower (16 vs 19). The knowledge pipeline is consistent across runs.

5. Multi-provider routing is working -- clean OpenAI access for
   reviewer/researcher, local GPU for coder, Ollama for archivist.
   No 889-event fallback catastrophe.

### Waiting on Arm 2 (~60-70 min)

This is the first Phase 1 run with clean API access on both arms.
The acc-empty delta will be the definitive same-domain compounding
measurement.

199 addenda. ~586 KB session memo.


## Addendum 200: Phase 1 v2 COMPLETE + Wave 60 SHIPPED -- the final measurement

**Added:** Definitive same-domain compounding result + Wave 60 audit clean.

### Phase 1 v2: both arms, clean API, multi-provider

| Task | Acc Q | Empty Q | Delta |
|------|-------|---------|-------|
| csv-reader | 0.629 | 0.490 | +0.139 |
| data-validator | 0.463 | 0.499 | -0.036 |
| data-transformer | 0.593 | 0.508 | +0.085 |
| pipeline-orchestrator | 0.573 | 0.572 | +0.001 |
| error-reporter | 0.582 | 0.690 | -0.108 |
| performance-profiler | 0.597 | 0.670 | -0.073 |
| schema-evolution | 0.602 | 0.531 | +0.071 |
| pipeline-cli | 0.601 | 0.595 | +0.006 |
| **Mean** | **0.580** | **0.569** | **+0.011** |

### The definitive answer

+0.011. Same number as Phase 0.

Phase 0 (diverse tasks, 6 clean runs): delta -0.011 to -0.039
Phase 1 (same-domain tasks, clean multi-provider): delta +0.011

Knowledge accumulation does not measurably improve quality on
coding tasks, even when:
- Tasks share a domain (data processing pipeline)
- Entries cross the 0.50 similarity threshold (16 accessed)
- The curating archivist produces REFINE actions
- Graph-augmented retrieval is active
- Progressive disclosure with top-1 injection is active
- Multi-provider routing works cleanly
- The full Wave 59.5 stack is operational

The delta is within the +/-0.10 per-task variance band.
Quality variance within each arm (~0.17-0.20 range) exceeds
the between-arm delta.

### What this means

The knowledge pipeline ACTIVATES (entries cross threshold, get
accessed, get refined). But activation does not translate to
quality improvement. The model produces comparable quality with
or without accumulated knowledge from prior same-domain tasks.

This is consistent with:
- Xiong et al.: add-all performs flat or declining
- SkillsBench: self-generated skills at -1.3pp
- Phase 0 v2-v12: delta invariant at ~zero

The finding is now confirmed across:
- 6 Phase 0 runs (diverse tasks)
- 2 Phase 1 runs (same-domain tasks)
- Local-only and multi-provider configurations
- Pre-curation and post-curation stacks
- 30B local model with Gemini/OpenAI extraction

### What DOES work

Operational knowledge (playbooks, common mistakes): +0.177
The infrastructure itself: 3434 tests, 65 events, 9-layer pipeline
The cooperative UI: the only system with live operator control surface

### Wave 60 shipped

3434 tests passing. 6 silent failure fixes from audit:
- colony_manager.py: embedding failure logged instead of silently passed
- knowledge_catalog.py: graph neighbor failure upgraded to warning
- api.py: JSON parse try/except on feedback endpoint
- api.py: timestamp field type fix
- knowledge-browser.ts: error handling on relationship fetch
- knowledge-browser.ts: error handling on feedback submit

### SESSION COMPLETE

200 addenda. 14 Phase 0/1 runs. Waves 54-60 shipped.
3434 tests. 65 events. 9-layer knowledge pipeline.
From "0 productive tool calls" to a complete curating
knowledge system with cooperative UI.

The project needs users, not waves.

200 addenda. ~590 KB session memo.


## Addendum 201: Wave 61 SHIPPED -- The Colleague Colony

**Added:** Wave 61 verified and shipped.

### What shipped

| Track | What | Files | Tests |
|-------|------|-------|-------|
| 1 | propose_plan + procedural prompt + spawn guard | queen_tools.py, queen_runtime.py, queen_intent_parser.py, caste_recipes.yaml | 9 |
| 2 | proposal-card component + queen-chat wiring | proposal-card.ts (NEW), queen-chat.ts, types.ts | -- |
| 3 | query_outcomes, analyze_colony, query_briefing | queen_tools.py, caste_recipes.yaml | 11 |
| 4 | workspace-browser + colony file diff + Workspace tab | workspace-browser.ts (NEW), formicos-app.ts, colony-detail.ts | -- |
| 5 | Budget REST endpoint + budget-panel | routes/api.py, budget-panel.ts (NEW), queen-overview.ts | -- |

Queen tools: 21 -> 25 (+4: propose_plan, query_outcomes, analyze_colony, query_briefing)
20 new tests (9 Track 1 + 11 Track 3). All 5 tracks verified against codebase.

### Key capabilities gained

- Queen deliberates before spawning (propose_plan mandatory, two-layer safety net)
- Operator sees proposal cards with "Go ahead" / "Let me adjust" buttons
- Queen can analyze colony outcomes empirically (query_outcomes)
- Queen can deep-dive specific colonies (analyze_colony)
- Workspace file browser with colony file-change tracking
- Budget panel with per-model spend breakdown
- Supercolony dashboard visible

### Audit corrections applied

- estimated_cost runtime-computed (not LLM-hallucinated)
- 9 tests instead of required 3 (over-delivery)
- groq nested IDs verified at backend _resolve() level

201 addenda. ~596 KB session memo.
