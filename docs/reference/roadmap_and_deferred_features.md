# Roadmap and Deferred Features Reference

Last updated: 2026-03-24. Source: audit of waves 1-61, ADRs 001-048,
specs, reference audits, FINDINGS.md.

FormicOS is a cooperative, editable, auditable brain/toolkit. The operator
must be able to see and edit everything the system knows and does. The
toolkit itself must be powerful and flexible enough to justify the
complexity. This document evaluates ~130 deferred features through that
lens.

---

## Ship Soon: Correctness and Credibility

These are bugs or gaps that make existing infrastructure fail silently.
Fixing them is prerequisite to trusting any measurement result.

### 1. Double-ranking pipeline: truncation before canonical scoring

**Problem:** `memory_store._rank_and_trim()` (memory_store.py:420-438)
sorts by raw Qdrant cosine score and truncates to `top_k` BEFORE
`knowledge_catalog.py` applies the full composite scoring formula
(0.38 semantic + 0.25 thompson + 0.15 freshness + 0.10 status + 0.07
thread + 0.05 cooccurrence + graph_proximity + pin_boost). The chain:

```
memory_store._search_qdrant_filtered()
  fetch top_k * 2 from Qdrant (raw cosine)
  _rank_and_trim(hits, top_k)         <-- FIRST TRUNCATION (cosine only)
knowledge_catalog._search_thread_boosted()
  merged.sort(key=_keyfn)             <-- SECOND SORT (7-signal composite)
  merged[:top_k]                      <-- SECOND TRUNCATION
```

The 2x over-fetch is the only protection. An entry ranked #15 by cosine
but #3 by the composite formula (e.g., high co-occurrence or thread bonus)
gets discarded before the composite ever sees it. The graph_proximity and
co-occurrence signals built in Waves 59-59.5 may never reach their best
candidates.

**Fix:** Increase over-fetch to 4x in `_search_qdrant_filtered` (1 line
change), OR pass the catalog's composite key into `_rank_and_trim` so it
applies the canonical sort (requires a callback parameter, ~20 lines).
The 4x over-fetch is the safe minimal fix.

**Impact:** Correctness of the core retrieval path. Every colony's
knowledge injection is affected.

### 2. Static retrieval query: same entries every round

**Problem:** `colony_manager.py:646-651` fetches knowledge once before
the round loop using `colony.task` as the query:

```python
knowledge_items = await self._runtime.fetch_knowledge_for_colony(
    task=colony.task, ...)
```

This list is passed unchanged to every `runner.run_round()` call (line
758). The only re-fetch trigger is a goal redirect (lines 703-713). The
agent may be debugging a specific error in round 3 — but the knowledge
injected is still optimized for the original task description from round 1.

**Fix:** Re-query with round context (e.g., last tool output summary or
current sub-goal) at the start of each round. ~30 lines in
`colony_manager.py`. The catalog search is fast (<100ms) so the
per-round cost is negligible.

**Impact:** May explain part of the +0.011 flatness in Phase 1 results.
Knowledge "activates" but the same 5 entries appear every round regardless
of what the agent is doing.

### 3. Domain filter structurally inert: primary_domain lost in normalization

**Problem:** The domain boundary filter in `context.py:543-548` checks
`item.get("primary_domain", "")`. But `_normalize_institutional` in
`knowledge_catalog.py:127-153` wraps raw entries into a `KnowledgeItem`
dataclass that has no `primary_domain` field — the key is silently dropped.
Every normalized entry returns `""` for `primary_domain`, which always
passes the filter. The domain boundary defense is structurally inert for
all institutional memory entries.

Additionally, 39% of entries have no `task_class` tag at all
(knowledge_flow_audit.md finding). Even if the filter worked, untagged
entries would bypass it.

**Fix:** Add `primary_domain` to `KnowledgeItem` (or pass it through as
an extra key during normalization). Then fix the tagger to handle the 39%
gap. ~20 lines across `knowledge_catalog.py` and `memory_extractor.py`.

**Impact:** The thing that prevented "Syllable Counting in a Rate Limiter"
(cross-domain contamination) is not actually working. Safety infrastructure
that silently fails is worse than no infrastructure.

### 4. Workspace executor container isolation

**Problem:** Colony code executed via `workspace_execute` runs on the
backend host process without container isolation. CLAUDE.md calls this
"the largest remaining security gap." The `code_execute` tool has proper
Docker sandboxing (`--network=none`, `--memory=256m`, `--read-only`) but
`workspace_execute` bypasses all of it when `WORKSPACE_ISOLATION=false`.

The Aider benchmark will run untrusted Exercism solutions inside the
container. Any evaluation by external users will flag this immediately.

**Fix:** Ensure `WORKSPACE_ISOLATION=true` is the default and the
workspace Docker execution path (`_execute_workspace_docker` in
sandbox_manager.py:444) works reliably. The code exists — it just needs
to be the enforced default, not an opt-in flag.

**Impact:** Security credibility. Prerequisite for external evaluation.

---

## Ship Medium-Term: Unlock Next-Level Capability

These features change how FormicOS feels to use. They build on
infrastructure that already exists.

### 5. Quality-based auto-escalation to cloud on local failure

**Problem:** When the local 30B model fails a task (low quality, repeated
stall, governance timeout), the colony just fails. The multi-provider
routing is built. The fallback chain in `LLMRouter._DEFAULT_FALLBACK`
(runtime.py:174-178) handles adapter errors but not quality failures.

**Current fallback triggers** (runtime.py:287-319):
- Provider in cooldown (ADR-024)
- `adapter.complete()` raises exception
- `result.stop_reason == "blocked"` (Gemini content filter)

**Missing trigger:** colony completes with quality < threshold.

**Design:** After colony completion, if `quality_score < 0.3` and rounds
were exhausted, re-spawn with the next model in the fallback chain. The
`ColonyOutcome` projection (ADR-047) already tracks success/failure per
model. This is policy (~100 lines in `colony_manager.py` or
`queen_runtime.py`), not architecture.

**Impact:** Directly addresses "local model is good enough for 70% of
tasks but terrible for 30%." The highest-leverage routing feature.

### 6. Progressive Queen model routing

**Problem:** The Queen on local 30B is a competent dispatcher but a
mediocre strategist. When the operator asks complex planning questions,
the Queen produces shallow responses. The per-caste routing already
supports independent Queen routing:

```yaml
# config/formicos.yaml line 32
models:
  defaults:
    queen: "anthropic/claude-sonnet-4-6"  # cloud for planning
    coder: "llama-cpp/gpt-4"              # local for execution
```

`resolve_model("queen", ws_id)` and `resolve_model("coder", ws_id)` are
called independently (runtime.py:862). Per-workspace override via
`WorkspaceConfigChanged` event (key `queen_model`) also works.

**Design:** Route the Queen to cloud for complex queries, keep coders
local. The Wave 61 `propose_plan` tool makes this natural — deliberation
goes to cloud, spawn confirmations stay local. ~30 lines of routing
policy. The `model_routing` table in formicos.yaml:574-586 exists but
is not wired into `resolve_model()` — activating it would give
caste-by-phase routing.

**Impact:** Makes "replace OpenClaw" viable. The Queen's intelligence
is the user-facing bottleneck.

### 7. Adaptive retrieval threshold

**Problem:** The 0.50 similarity threshold for knowledge injection is
static, calibrated by trial and error. It correctly prevents cross-domain
contamination but may be too aggressive for within-domain tasks where
even medium-similarity entries are useful.

**Design:** A threshold that learns from colony outcomes: lower when
injection correlated with success, raise when it correlated with failure.
The Bayesian machinery for this already exists in the Thompson Sampling
confidence system. The `knowledge_feedback` tool provides explicit
signal. ~50 lines in `knowledge_catalog.py`.

**Impact:** Tunes the knowledge pipeline's sensitivity automatically.

### 8. Negative signal extraction

**Problem:** The knowledge pipeline only extracts what worked. It never
extracts what FAILED. "Don't use recursive approach for this problem
type — it stack overflows on inputs > 1000" is more valuable than
"recursive approach works for small inputs." Failure patterns are the
operational knowledge category where playbooks proved +0.177.

**Current state:** `memory_extractor.py` only runs on successful
colonies. Failed colonies produce no knowledge entries.

**Design:** Extend the extraction prompt to handle failed colonies
with a "what went wrong and what should be avoided" frame. Route
failed-colony transcripts through extraction with a `learning` sub-type
and conservative priors. ~50 lines in extraction prompt + routing logic.

**Impact:** The single highest-value knowledge type for compounding.
Operational "don't do X" knowledge is exactly what the model doesn't
have from training data.

### 9. Tool surface reduction per caste

**Problem:** The coder caste has 16 tools. Research literature (including
Qwen3 documentation) consistently shows tool-calling reliability degrades
above 6-8 tools for models in the 30B parameter range.

**Current tool counts** (caste_recipes.yaml):
- Queen: 21 tools (line 178)
- Coder: 16 tools (line 227)
- Reviewer: 9 tools (line 277)
- Researcher: 9 tools (line 335)
- Forager: 3 tools (line 384)
- Archivist: 4 tools (line 418)

**Tool filtering path:** `caste_recipes.yaml` `tools:` list is the
primary control surface. `CASTE_TOOL_POLICIES` in tool_dispatch.py:571
acts as a safety backstop. `check_tool_permission()` at line 613
enforces both layers.

**Design:** Reduce coder to core 6 tools (memory_search, code_execute,
workspace_execute, read_workspace_file, write_workspace_file, patch_file)
with git and knowledge tools available on-demand via a `request_tool`
meta-tool. Reviewer and researcher are already at 9 — acceptable.

**Impact:** Reliability improvement for the workhorse caste.

### 10. Evolvable extraction prompts

**Problem:** The extraction prompt is static. After N colonies, it may
produce entries that are consistently low-quality or non-transferable.
The HyperAgents insight: evaluate whether the extraction prompt produces
useful entries, and if not, rewrite it. Track versions.

**Design:** After every 50 colonies, compare extraction quality metrics
(entries accessed vs produced ratio, feedback positive rate, decay rate).
If quality is declining, trigger an archivist colony to propose a prompt
revision. Store prompt versions in events. ~100 lines.

**Prerequisite:** Fix the retrieval bugs (#1-3) first. Optimizing
extraction while retrieval is broken optimizes a pipeline with a hole
in it.

---

## Ship When Needed: Real but Not Blocking

### 11. Contradiction duels

The Queen spawns two colonies with opposing hypotheses, evaluates both,
admits the winner with higher confidence. Maps to existing
`spawn_parallel` + governance. Requires Wave 61 Queen deliberation mode.
Compelling demo, genuine capability gap. ~200 lines.

### 12. Federation testing

Federation adapter, CRDT replication, and peer trust are all built and
untested. Two FormicOS instances sharing knowledge is the multi-hive
architecture nobody else has. Needs a second Docker stack or machine.
Demo opportunity and differentiator.

### 13. Event store snapshotting

Replay from event zero gets slow as the event log grows. Periodic
projection snapshots ("here's state at event 50,000, replay from here")
is standard event-sourcing practice. Not urgent at current scale
(hundreds of events), will become urgent with real usage (thousands).

### 14. Bootstrap confidence intervals for eval

The eval harness runs experiments but has no statistical rigor — no CIs,
no paired comparisons. With the Aider benchmark producing real data, this
becomes immediately useful for significance testing. ~200 lines in a new
`eval/stats.py`.

### 15. Operator feedback loop (thumbs up/down on entries)

No human input channel to knowledge confidence. Every competitor has one.
FormicOS does not. The `knowledge_feedback` tool exists for agents but
there's no operator-facing UI to approve/reject/flag entries. Wave 60
dispatched this but status unclear.

### 16. Playwright Level 3 browser rendering

The fetch pipeline handles static HTML. JS-heavy pages return garbage.
Would meaningfully expand web foraging coverage. Requires a headless
browser sidecar container. Deferred 4 waves (44-47). Ship when foraging
coverage becomes a measured bottleneck.

### 17. Search traffic through EgressGateway

`web_search.py` uses its own `httpx.AsyncClient`, bypassing
EgressGateway's rate/domain/robots.txt policy. Search requests are
uncontrolled. ~30 lines to route through the gateway.

### 18. Learned routing from outcome history

`ColonyOutcome` projections (ADR-047) track success rate, cost, rounds,
strategy, and caste composition per colony. This data is never fed back
into model/strategy selection. The router could learn "coder tasks with
sequential strategy complete in 2.1 rounds avg vs 3.8 for stigmergic"
and route accordingly. Most repeatedly deferred feature in the codebase
(waves 42, 43, 45, 46). ~200 lines in routing policy.

### 19. Thompson Sampling over forager query strategies

The TS engine governs knowledge retrieval scoring. The same machinery
could pick which query template yields the best web results per gap type.
The forager already has multiple templates — they're just cycled, not
selected intelligently. ~100 lines.

### 20. Sysbox/gVisor container isolation

Stronger isolation for the Docker socket/nested container problem. The
current Docker socket proxy is a mitigation, not a fix. Ship when
deploying for external users who need security guarantees.

---

## Explicitly Do NOT Ship

These are correctly deferred. Building them now would be premature
optimization or solutions looking for problems.

### RL / self-evolution / experimentation engine

Deferred 11 waves (8-36). The measurement arc proved that knowledge
compounding doesn't help on training-data tasks (+0.011 delta). Adding
an RL loop on top of a system that produces +0.011 is optimizing a zero.
Fix the retrieval bugs, get the Aider benchmark result, THEN revisit
whether self-evolution has signal to optimize.

### Full A2A / AG-UI protocol conformance

Protocol compliance for protocols nobody is consuming. Build when someone
wants to connect to FormicOS via A2A, not before.

### Multi-hop graph traversal

No evidence 1-hop is insufficient. The graph_proximity signal is weighted
at 0.06. Making it 2-hop doubles the neighbor set for marginal impact.

### Kubernetes / multi-node deployment

Single-machine Docker Compose is the right deployment for a pre-launch
project. Kubernetes is for horizontal scaling with real users.

### Visual workflow canvas editor

10+ waves deferred. Months of frontend work for power users who don't
exist yet.

### SGLang inference server

Considered and abandoned by wave 17. llama.cpp with CUDA graphs is
the established local inference path.

### HDBSCAN meta-skill synthesis

Never shipped, never missed. The knowledge pipeline's extraction +
distillation path handles consolidation without batch clustering.

### DSPy / GEPA prompt optimization

Automated prompt optimization on top of a 30B local model adds
complexity without evidence of benefit at this scale.

### DGM-style self-modification

The system modifying its own code based on performance. Explicitly
excluded. The risk/reward ratio is wrong for a pre-launch system.

### Multi-user / auth / billing

Single-operator by design. Build when there are multiple operators.

### LLM-based context summarization

Deferred to post-alpha when Compute Router can route to a cheap local
model. The context tier system (budget-aware assembly) handles this
deterministically for now.

### Binary file support (PDF, images)

Deferred since ADR-029 / wave 16. Text-only remains sufficient for
the current task portfolio.

---

## Priority Stack

If picking 5 in order:

1. **Fix double-ranking truncation + static retrieval** — correctness
   bugs that make existing infrastructure fail silently (~50 lines)
2. **Fix domain filter normalization gap** — safety infrastructure that
   silently does nothing (~20 lines)
3. **Quality-based auto-escalation to cloud** — highest-leverage routing
   feature, infrastructure already built (~100 lines)
4. **Negative signal extraction** — the knowledge type most likely to
   compound, since it's genuinely new to the model (~50 lines)
5. **Route Queen to cloud for complex queries** — user-facing
   intelligence bottleneck, config change + ~30 lines of policy

Items 1-2 are bug fixes. Items 3-5 are the features that change how
FormicOS feels to use. Everything else waits for users to tell you what
they need.

---

## Full Catalog by Theme

For the complete list of all ~130 deferred items with wave-by-wave
provenance, see the wave plan documents in `docs/waves/` and ADRs in
`docs/decisions/`. This document covers the items that matter for
shipping a credible, usable system.
