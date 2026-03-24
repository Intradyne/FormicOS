# Knowledge as Pheromone

## A Two-Layer Stigmergic Architecture for FormicOS

Authoring context: post-Wave 36 FormicOS, grounded against the live codebase in
March 2026.

---

## Executive Summary

The core claim of this memo is that FormicOS's knowledge system is no longer
just "memory." It is already an environmental coordination substrate with the
right primitives to behave like a pheromone field:

- traces are deposited by colony work (`MemoryEntryCreated`, knowledge access,
  transcript harvest, distillation, federation);
- traces decay over time (`DecayClass`, gamma-decay at query time);
- traces are reinforced by successful use (`MemoryConfidenceUpdated`,
  co-occurrence reinforcement, positive feedback);
- traces are bounded and filtered by status, confidence, and maintenance
  policies;
- traces are sampled stochastically (`random.betavariate(alpha, beta)` in
  retrieval), not greedily consumed.

That matters because classical stigmergy is not "shared state" in the generic
software sense. It is a coordination mechanism built on deposition,
evaporation, reinforcement, and probabilistic response to traces in the
environment. Most contemporary LLM multi-agent frameworks stop at message
passing, shared logs, or retrieval memory. FormicOS is closer to a genuine
stigmergic substrate because its environment has dynamics.

The second claim is architectural: FormicOS already has two stigmergic layers.

1. The short-timescale, intra-colony layer lives in
   [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py)
   and
   [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py).
   It routes information among agents using a round-local, pheromone-weighted
   topology.
2. The long-timescale, inter-colony layer lives in
   [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py),
   [src/formicos/core/crdt.py](/c:/Users/User/FormicOSa/src/formicos/core/crdt.py),
   [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py),
   [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py),
   and
   [src/formicos/surface/self_maintenance.py](/c:/Users/User/FormicOSa/src/formicos/surface/self_maintenance.py).
   It coordinates colonies over time through a persistent, confidence-weighted,
   self-maintaining knowledge environment.

At the moment, these two layers interact only partially. Layer 1 influences
Layer 2 because colony success and failure update knowledge confidence and
extract new entries. Layer 2 influences Layer 1 only weakly, mostly through
prompt/context injection and retrieval. The highest-leverage next step is to
close that loop explicitly without destabilizing the event-sourced core.

The most important practical conclusion for Wave 37+ is this:

FormicOS should not replace its Queen with "pure stigmergy." It should keep the
Queen as a sparse, global controller and make the knowledge substrate the main
adaptive medium through which colonies learn how to coordinate locally.

That implies a prioritized roadmap:

1. **Knowledge-weighted topology initialization**. Let relevant, high-confidence
   knowledge bias initial intra-colony routing.
2. **Outcome-weighted knowledge reinforcement**. The colony outcome loop exists
   already; make it stronger and quality-aware.
3. **Adaptive evaporation by domain**. The current `decay_class` system is the
   right hook; tune it from actual usage and prediction error patterns.
4. **Stigmergic colony-configuration suggestions**. Let the environment suggest
   likely-effective colony shapes instead of making the Queen infer them from
   scratch every time.
5. **Cross-colony trace inheritance**. Propagate successful topology motifs into
   continuation colonies.
6. **Branching-factor stagnation detection**. Detect premature convergence at
   both routing and knowledge levels before the system saturates.

None of the top four require new event types. All can be implemented in the
existing engine/surface seams.

One final grounding note: the prompt that commissioned this memo referred to
`engine/topology.py`. The current live equivalent seam is
[src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py).

---

## 1. The Knowledge-as-Pheromone Mapping

### 1.1 Classical ACO in compact form

In standard Ant Colony Optimization (ACO), an ant chooses the next component
`j` from state `i` with probability

`P_ij^k \propto [tau_ij]^alpha [eta_ij]^beta`

where:

- `tau_ij` is pheromone strength,
- `eta_ij` is heuristic desirability,
- `alpha` weights pheromone,
- `beta` weights heuristic information.

Pheromone then evolves as

`tau_ij <- (1 - rho) tau_ij + sum_k Delta tau_ij^k`

where `rho` is evaporation and `Delta tau_ij^k` is reinforcement, usually tied
to solution quality. Dorigo and colleagues established this for the Ant System
family; ACS adds a local update rule and global-best reinforcement; MMAS adds
explicit `tau_min` and `tau_max` bounds to avoid saturation and stagnation
[1][2][3].

What matters here is not the TSP-specific form. It is the coordination logic:
environmental traces bias future action, but traces also decay, and the system
does not deterministically choose the strongest trace every time.

### 1.2 The exact FormicOS mapping

The cleanest way to map FormicOS to ACO is to stop treating a knowledge entry as
"a note" and instead treat it as a **distributional pheromone trace**.

| Classical stigmergy concept | FormicOS equivalent | Where it lives |
|---|---|---|
| Trace location | Knowledge entry or entry cluster | `MemoryEntry`, co-occurrence graph |
| Trace strength | Posterior mean `mu = alpha / (alpha + beta)` | `MemoryEntry.conf_alpha/conf_beta` |
| Trace certainty | Posterior mass `s = alpha + beta` | same |
| Evaporation | Query-time gamma-decay toward prior | `core/crdt.py`, confidence update logic |
| Probabilistic response | Thompson draw from `Beta(alpha, beta)` | `knowledge_catalog.py` |
| Heuristic bias | semantic similarity, freshness, status, thread bonus | `knowledge_catalog.py` |
| Multi-trail interaction | co-occurrence reinforcement and cluster scoring | `knowledge_catalog.py`, `projections.py` |
| Trail repair | proactive intelligence + maintenance dispatcher | `proactive_intelligence.py`, `self_maintenance.py` |
| Trail aggregation | distillation / merge synthesis | `self_maintenance.py`, memory merge flows |

The key formal difference from classical ACO is that FormicOS does not store a
single scalar `tau_e` per trace. It stores a posterior over reliability.

For an entry `e`, define:

- expected quality signal:
  `mu_e = alpha_e / (alpha_e + beta_e)`
- trace certainty / evidence mass:
  `s_e = alpha_e + beta_e`
- sampled response signal:
  `x_e ~ Beta(alpha_e, beta_e)`

Then the current retrieval system is already close to a stochastic transition
rule:

`Score(e | q) =`
`  w_sem * semantic(q, e)`
`+ w_th * x_e`
`+ w_fresh * freshness(e)`
`+ w_status * status_bonus(e)`
`+ w_thread * thread_bonus(e)`
`+ w_cooc * cooccurrence(e, R)`

where `R` is the current result set and `x_e` is a Thompson sample. In code,
this happens in
[src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py),
where the ranking function explicitly draws `random.betavariate(alpha, beta)`.

This is stricter than most "memory" systems:

- not just semantic retrieval,
- not just recency weighting,
- not just importance weighting,
- but a **probabilistic policy over environmental traces**.

### 1.3 Beta confidence is not merely concentration

The prompt framed `Beta(alpha, beta)` as pheromone concentration. That is useful
but incomplete. In FormicOS, the Beta posterior represents two different
stigmergic properties at once:

1. **Expected desirability**: how good the entry is expected to be if reused.
2. **Confidence / certainty**: how much validated evidence supports that
   expectation.

This makes FormicOS's environmental trace richer than a standard scalar trail.
Two entries may have the same mean but different uncertainty:

- `Beta(6, 4)` and `Beta(60, 40)` both have mean `0.6`,
- but the second should dominate under exploitation and the first should be
  explored under uncertainty-aware sampling.

In other words: FormicOS's environment carries both **intensity** and
**epistemic uncertainty**. Standard ACO usually encodes only intensity.

That is one reason the thesis is compelling. The knowledge layer is not merely
ACO-like; it is a more expressive stigmergic medium than classical trail
scalars.

### 1.4 Evaporation in FormicOS is closer to adaptive trail decay than archive pruning

In classical ACO, evaporation is usually explicit and global:

`tau <- (1 - rho) tau`

FormicOS instead computes effective confidence at query time:

`alpha_e(t) = alpha_0 + sum_i gamma_e^(Delta t_i) * success_i`
`beta_e(t)  = beta_0  + sum_i gamma_e^(Delta t_i) * failure_i`

where `gamma_e` depends on `decay_class`:

- `ephemeral`: `gamma = 0.98`
- `stable`: `gamma = 0.995`
- `permanent`: `gamma = 1.0`

This is implemented in
[src/formicos/core/crdt.py](/c:/Users/User/FormicOSa/src/formicos/core/crdt.py)
and mirrored in colony-level confidence updates in
[src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py).

This design has a strong theoretical advantage. It separates:

- monotonic replicated facts (success counts, failure counts, timestamps), from
- non-monotonic derived confidence (decayed posterior at read time).

That is exactly the right move for an event-sourced, federated stigmergic
system. It lets the environment remain mergeable while still behaving like an
evaporating trace field.

### 1.5 Co-occurrence is a genuine multi-pheromone effect

Classical ACO usually assumes one trail family over a graph. Later variants
introduce multiple pheromones when different objectives or interacting
attributes must be balanced. FormicOS already has this in practical form:

- the direct entry signal,
- the thread-local signal,
- the status signal,
- the freshness signal,
- the Thompson-sampled confidence signal,
- the co-occurrence cluster signal.

The co-occurrence term matters because it lets traces reinforce each other as a
cluster instead of acting as isolated items. That is much closer to how real
pheromone systems compose: a path is rarely just one scalar; it is a field with
interacting local gradients and environmental context.

### 1.6 Comparison to Ant System, ACS, and MMAS

#### Ant System

The original Ant System is a positive-feedback search process with evaporation
and probabilistic action selection [1]. FormicOS's knowledge layer matches that
logic closely, but with two major upgrades:

- traces are posterior distributions rather than scalar deposits,
- and response depends on multiple signals, not just `tau` and `eta`.

#### ACS

ACS distinguishes between local updates and global best-tour reinforcement [2].
FormicOS has an analogue:

- **local-ish effects**:
  retrieval-time co-occurrence reinforcement, thread bonuses, immediate
  `knowledge_feedback`;
- **global-ish effects**:
  colony success/failure updating accessed entries, distillation, proactive
  maintenance.

The fit is not one-to-one, but the pattern is strong: there is a short loop
that nudges traces during use and a slower loop that reinforces traces from
whole-colony outcomes.

#### MMAS

MMAS adds explicit `tau_min` and `tau_max` bounds to avoid early lock-in and
stagnation [3]. FormicOS already applies this idea clearly at Layer 1: the
intra-colony pheromone edge weights are clamped to `[0.1, 2.0]`, with
evaporation and strengthen/weaken updates in
[src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py).

The current live implementation is:

- edge decay toward neutral:
  `w <- 1.0 + (w - 1.0) * 0.95`
- strengthen active progressing edges by `1.15`
- weaken warned/halting edges by `0.75`
- clamp to `[0.1, 2.0]`

That is effectively an MMAS-style bounded short-term pheromone layer.

Layer 2 lacks an equally explicit bound on long-run trace dominance. The Beta
prior, decay, status gating, and Thompson sampling together act as a soft bound,
but they are not as direct as MMAS. That gap is one reason adaptive decay and
branching-factor diagnostics are attractive proposals.

### 1.7 What theory predicts

**Proven in ACO literature**

- positive reinforcement without evaporation causes saturation and stagnation
  [1][3];
- bounded trails delay but do not eliminate premature convergence [3];
- convergence to optimum can be proved for some ACO families under strong
  conditions, but convergence speed and practical stagnation remain separate
  issues [4][5].

**Strong theoretical prediction for FormicOS**

Because FormicOS uses posterior sampling instead of greedy confidence ranking,
it should resist premature convergence better than a deterministic shared-state
memory system. Thompson sampling is doing the exact job ACO needs from
stochasticity: keep exploiting validated traces while still probing uncertain
ones.

**Practical prediction**

If outcome-weighted reinforcement grows faster than decay and sampling noise,
the knowledge layer will still saturate into a narrow attractor. That will look
like:

- repeated retrieval of the same entries,
- rising co-occurrence concentration,
- falling diversity of successful colony configurations,
- rising maintenance interventions in the same domains,
- and eventually, lower marginal returns from "high confidence" knowledge.

That is a textbook stagnation pattern, just expressed in a richer medium.

---

## 2. The Two-Layer Stigmergy Architecture

### 2.1 Layer 1: intra-colony stigmergy

FormicOS already implements a short-timescale, within-colony stigmergic
mechanism.

The routing substrate lives in
[src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py).
At each round:

1. agents emit lightweight "need" and "offer" descriptors,
2. embeddings are computed,
3. pairwise similarities are built,
4. similarities are multiplied by existing pheromone edge weights,
5. edges are thresholded at `tau`,
6. inbound degree is capped by `k_in`,
7. a DAG-like execution schedule is produced.

The result is a round-local communication topology, not a fixed team graph.

This is exactly the right role for short-term pheromone:

- it tunes who influences whom within a colony,
- on the timescale of rounds,
- using recent performance,
- without becoming permanent organizational structure.

### 2.2 Layer 2: inter-colony stigmergy

The knowledge layer is already doing the long-timescale counterpart:

- entries persist beyond a single colony,
- confidence evolves through success/failure,
- decay reduces stale influence,
- co-occurrence forms clusters,
- distillation compresses dense areas,
- federation replicates traces across instances,
- proactive intelligence and maintenance repair degraded areas.

This is not agent-to-agent routing. It is colony-to-colony coordination via a
shared environment.

That is the deeper point of the thesis: FormicOS's real stigmergic substrate is
not only the DyTopo edge-weight system. It is the environmental memory field
that makes one colony's validated work available as a biased affordance for the
next colony.

### 2.3 The current interaction between the two layers

Today, the coupling is asymmetric.

#### Layer 1 -> Layer 2

This loop already exists and is meaningful:

- colonies retrieve knowledge;
- accesses are recorded (`KnowledgeAccessRecorded`);
- colony outcomes update confidence on accessed entries;
- extracted knowledge becomes new entries;
- co-occurrence is reinforced from retrieval and reuse patterns;
- `ColonyOutcome` summarizes the result of whole-colony behavior.

In practical terms, Layer 1 already leaves marks in Layer 2.

#### Layer 2 -> Layer 1

This loop exists, but weakly:

- retrieved entries shape prompts and working context,
- thread-scoped retrieval narrows relevance,
- proactive insights can influence Queen decisions,
- but the knowledge layer does not yet directly bias topology initialization or
  per-round edge adaptation.

This is the missing connection. The environment informs what agents read, but
not yet how agents are connected.

### 2.4 Why multi-scale stigmergy is biologically plausible

Theraulaz and Bonabeau distinguish quantitative and qualitative stigmergy and
trace how local traces compound into colony-scale behavior [6]. Theraulaz and
colleagues' work on nest construction shows that social insects routinely
coordinate across multiple scales: trail-level traces, building cues, and
emergent nest structure are not the same phenomenon, but they are coupled [7].

That maps neatly onto FormicOS:

- Layer 1 is trail-like, fast, tactical, and local.
- Layer 2 is nest-like, slow, structural, and cumulative.

Parunak's work on digital pheromones and human-human stigmergy is also useful
here: environmental coordination can be mediated through multiple artifact
layers, not one global trail [8].

The architectural implication is clear. FormicOS should not collapse these two
scales into one universal score. It should let them remain distinct but
interactive:

- short-term topology pheromones should stay lightweight and fast-changing,
- long-term knowledge pheromones should stay persistent and confidence-aware.

### 2.5 Why the Queen should stay

Pure stigmergic systems work best when agents are simple and the environment can
absorb most of the coordination burden. LLM agents are the opposite:

- individually expensive,
- semantically expressive,
- prone to local rhetorical loops,
- and often capable of acting in ways that are globally sensible only with
  sparse oversight.

This is where FormicOS's hybrid architecture is right.

The Queen is not an embarrassment to stigmergy. The Queen is the boundary
condition that keeps an LLM colony from misusing an otherwise powerful
stigmergic substrate.

The right division of labor is:

- the Queen sets goals, constraints, decompositions, and interventions;
- the environment carries validated local coordination knowledge;
- colonies and agents adapt within those bounds.

That is closer to "stigmergy plus sparse governance" than to either pure
emergence or pure orchestration.

### 2.6 Comparison to current LLM multi-agent frameworks

This distinction also explains why FormicOS's knowledge system matters more than
the shared-state mechanisms found in many current frameworks.

- **MetaGPT** organizes role-specialized agents and artifacts around a software
  company metaphor, but the public framework centers on explicit role
  coordination, logs, and artifact passing, not a decaying,
  uncertainty-calibrated environmental trace field [9].
- **LangGraph** exposes powerful shared state and durable execution through
  `StateGraph`, checkpointers, and per-thread state persistence, but state is a
  neutral substrate unless the developer adds stigmergic dynamics on top [10].
- **CrewAI** exposes short-term, long-term, and entity memory, but the public
  memory model is still memory as storage and recall, not memory as bounded,
  evaporating, outcome-calibrated environmental pressure [11].

These systems are not wrong. They simply stop one layer earlier. FormicOS's
distinctive move is to turn memory into a self-updating trace medium.

### 2.7 Current implementation reality: what is already coupled, and what is not

It is worth being explicit about the current live architecture, because the
proposals in this memo are not asking FormicOS to become stigmergic. They are
asking it to complete a stigmergic loop it already partially implements.

#### What is already true in code

Layer 1 already has a working short-term pheromone system:

- `StigmergicStrategy.resolve_topology()` multiplies semantic compatibility by
  stored edge weights before thresholding.
- `RoundRunner._update_pheromones()` evaporates every existing edge toward
  neutral, then strengthens or weakens currently active edges.
- active edge weights are bounded, so no single route can explode without limit.

Layer 2 already has a working long-term environmental update system:

- retrieved knowledge is traced through `KnowledgeAccessRecorded`,
- successful and failed colonies update accessed entries,
- co-occurrence is reinforced from retrieval and reuse,
- proactive intelligence watches the field for contradiction, coverage gaps,
  and stale regions,
- self-maintenance can turn those detections into corrective colonies,
- federation moves confidence-bearing traces across instances without losing
  mergeability.

This means the system already has both deposition and evaporation at both
timescales. That is enough to say that FormicOS is not a mere shared-state
system. It is already operating as a layered stigmergic architecture.

#### What is not yet coupled

The current blind spots are specific.

1. **Knowledge does not initialize topology**.
   The colony begins with a neutral social graph plus semantic descriptors, not
   a graph already informed by what the environment has learned about this
   domain.

2. **Outcome reinforcement is still coarse**.
   The success/failure loop exists, but it does not yet weight reinforcement by
   colony quality strongly enough to distinguish a marginal success from a clean,
   tool-verified success.

3. **The environment does not yet recommend social form strongly enough**.
   `ColonyOutcome` exists, but the environment does not yet tell the Queen,
   "this class of task usually succeeds with this colony shape."

4. **The system detects some stagnation, but not field narrowing**.
   Stall detection exists inside colonies and insight rules exist at the
   knowledge level, but there is no unified measure of "the search space is
   collapsing around one narrow attractor."

That list is useful because it shows how constrained the next wave can be. The
missing work is not a new architecture. It is mostly about wiring the existing
knowledge field into the existing topology and governance loops more directly.

---

## 3. What the Solved Knowledge System Specifically Enables

This section links FormicOS's existing knowledge features to known ACO failure
modes.

### 3.1 Confidence-calibrated retrieval

Current capability:

- entries carry `Beta(alpha, beta)`,
- retrieval samples from the posterior,
- success and failure update those parameters.

What it enables:

- entries are retrieved in proportion to validated usefulness, not just lexical
  similarity;
- the system distinguishes "promising but uncertain" from "proven and stable."

ACO failure mode addressed:

- **premature exploitation**. Deterministic reuse of a top-ranked memory item is
  analogous to overcommitting to one path too early. Thompson sampling weakens
  that trap.

### 3.2 Decay classes and gamma-decay

Current capability:

- `ephemeral`, `stable`, `permanent` classes,
- query-time decay toward prior,
- explicit capped elapsed-day handling.

What it enables:

- stale traces lose influence without explicit deletion,
- domains with different temporal properties can coexist,
- federation remains monotonic while effective trust stays time-sensitive.

ACO failure mode addressed:

- **pheromone saturation** and **outdated-trace lock-in**. Classical ACO needs
  evaporation to forget old paths; FormicOS already does that at the confidence
  level.

### 3.3 Thompson sampling

Current capability:

- one posterior draw per candidate at retrieval time.

What it enables:

- balanced exploration of uncertain entries,
- opportunistic discovery of underused but promising knowledge,
- diversity preservation without randomizing the whole retrieval stack.

ACO failure mode addressed:

- **stagnation after early reinforcement**. This is arguably the single most
  important solved piece. Many "AI stigmergy" systems never got a credible
  exploration policy.

### 3.4 Co-occurrence reinforcement

Current capability:

- pairwise reinforcement of jointly retrieved entries,
- sigmoid-normalized co-occurrence score,
- cluster-aware surfacing and distillation candidate generation.

What it enables:

- compositional traces rather than isolated nuggets,
- reuse of knowledge ensembles,
- support for multi-part reasoning patterns.

ACO failure mode addressed:

- **single-trail blindness**. Tasks are often solved by patterns of jointly
  useful knowledge. Co-occurrence gives the environment a way to learn these
  combinations.

### 3.5 Proactive intelligence

Current capability:

- the original Wave 34 system had 7 deterministic knowledge-health rules;
- the current live code has those 7 plus 4 performance-style rules, for 11 total;
- contradiction, coverage, staleness, federation, merge, and outcome patterns
  can generate insights and suggested colonies.

What it enables:

- the system detects degradation before a human notices repeated failures,
- maintenance action becomes targeted rather than ad hoc,
- the Queen receives environment-level health signals.

ACO failure mode addressed:

- **undetected stagnation**. Classical ACO often discovers stagnation only via
  failing optimization performance. FormicOS has a chance to detect it through
  trace health diagnostics before task performance collapses.

### 3.6 Self-maintenance and autonomy levels

Current capability:

- `suggest`, `auto_notify`, `auto_execute`-style autonomy levels,
- budgeted dispatch,
- maintenance colony caps,
- scheduled triggers for staleness, domain health, and distillation refresh.

What it enables:

- adaptive repair of degraded trace regions,
- bounded automatic intervention,
- controlled self-healing rather than passive decay.

ACO failure mode addressed:

- **static evaporation schedules in dynamic environments**. Mavrovouniotis and
  Yang's dynamic-environment work is relevant here: fixed evaporation is often
  suboptimal when the environment itself changes [12]. FormicOS can already
  dispatch active repair instead of relying only on passive decay.

### 3.7 Knowledge distillation

Current capability:

- dense related clusters can be synthesized by archivist colonies.

What it enables:

- compression of dense local trace neighborhoods,
- improved retrieval from clusters that would otherwise fragment,
- partial reset of redundant trace saturation.

ACO failure mode addressed:

- **trace fragmentation**. Distillation is a useful answer to the fact that
  repeated reinforcement often creates many slightly different trail fragments
  instead of one strong, usable path.

### 3.8 Federation with CRDTs

Current capability:

- `ObservationCRDT`,
- per-instance success/failure counters,
- query-time decay,
- trust discounting and conflict handling.

What it enables:

- multi-instance environmental memory without losing mergeability,
- transport of validated traces across "nests",
- trust-aware reuse of foreign experience.

ACO failure mode addressed:

- **local optima at the single-colony or single-instance level**. Federation
  gives the substrate a path to escape local minima by importing structured
  experience from elsewhere.

### 3.9 Why this matters more than the topology layer alone

DyTopo-style routing helps a colony decide who should talk to whom during one
task. That matters, and the benchmark evidence is already strong. But without a
long-term stigmergic substrate, every colony starts from near-zero social
memory. The system can optimize communication shape but not accumulate verified
coordination knowledge about domains, strategies, or colony configurations.

The FormicOS knowledge layer changes that. It turns one successful colony into a
trace that can bias many future colonies.

That is why the knowledge system is not just adjacent to stigmergy. It is the
part that makes stigmergy compound over time.

### 3.10 Why truthful outcome labeling is now part of the substrate

There is one subtle but important post-Wave-36 point that belongs in the theory:
the value of a stigmergic environment depends on the truthfulness of the reward
signal that updates it.

Before the recent governance fix, a coding colony could solve its task, execute
correct code successfully, and still be labeled as failed because the
convergence detector only saw repetitive text and interpreted it as stall. That
was not just a UX bug. It was a substrate bug. If solved work is labeled failed,
then:

- useful entries receive the wrong posterior update,
- `ColonyOutcome.succeeded` becomes unreliable,
- performance insights become misleading,
- and the environment starts to punish the very traces that made success
  possible.

In ACO terms, that is equivalent to rewarding the wrong trail. A pheromone
system with an inverted or noisy reward channel does not merely become less
efficient. It can become actively adversarial to itself.

The recent live fix in
[src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
matters because it reclassifies stable repeated output after successful
`code_execute` as completion evidence instead of stall evidence. That restores
the integrity of the global reinforcement loop for coding tasks. FormicOS still
needs a more general non-code completion signal eventually, but the system is no
longer poisoning its own knowledge field on the core demo path.

This is why outcome-weighted reinforcement is now a viable Wave 37 proposal.
Without truthful colony outcomes, it would have been too dangerous to amplify
the effect of success and failure at the knowledge layer.

---

## 4. Concrete Architectural Improvements

This section prioritizes implementable changes by impact-to-effort ratio and
keeps them inside the current FormicOS layering rules.

### 4.1 Proposal A: Knowledge-weighted topology initialization

#### Thesis

When a colony spawns, the initial DyTopo graph should not be knowledge-blind.
Relevant, high-confidence knowledge should bias the initial edge weights between
agents before any round-level pheromone adaptation begins.

Right now, Layer 2 influences Layer 1 mostly through prompts. This proposal
lets the environment influence routing directly.

#### Concrete code changes

Primary files:

- [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- optionally
  [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)
  for surfacing the bias explanation

Suggested data-path change:

1. At colony start, compute a small "knowledge bias summary" from the already
   retrieved entries:
   - dominant domains,
   - average posterior mean per domain,
   - posterior mass / certainty per domain,
   - recent successful colony strategies in those domains.
2. Map those domains onto agent descriptors:
   - a coder handling a code-heavy task receives stronger affinity to other
     agents whose recipes historically co-occur with successful code-domain
     traces,
   - an archivist may get stronger inbound edges if the domain has high
     documentation or synthesis density.
3. In `StigmergicStrategy.resolve_topology`, apply a multiplicative prior to the
   similarity matrix before thresholding:

   `sim_ij <- sim_ij * prior_ij`

   where `prior_ij` is derived from domain trace quality, capped within a narrow
   range such as `[0.85, 1.15]`.

No new event types are required. This can be derived from retrieval state at
spawn time and used as a runtime prior.

#### Expected improvement

- fewer warmup rounds before useful agent routing emerges,
- lower token cost on repeated-domain tasks,
- better early-round convergence,
- improved performance on tasks where the system already has validated
  institutional memory.

#### How to measure it

- change in rounds-to-first-successful-tool-use,
- change in total rounds,
- change in token/output cost,
- success rate on repeated-domain HumanEval or SWE-bench slices,
- topology sparsity and edge reuse stability.

#### Risks

- over-biasing toward stale institutional habits,
- reduced discovery of new team shapes,
- making the topology too dependent on retrieval errors.

#### Mitigation

- keep bias small,
- gate it by posterior mass and freshness,
- compare against an ablation with zero bias,
- expose the applied prior in debug/score breakdown form for inspection.

#### Precedent

- classical `eta` heuristic term in ACO [1][2],
- task-adaptive topology design in G-Designer [13],
- semantic-routing topology in DyTopo [14].

#### Priority

High impact, medium effort.

### 4.2 Proposal B: Outcome-weighted knowledge reinforcement

#### Thesis

FormicOS already updates accessed entries based on colony success and failure.
That is the right loop, but it is too coarse. Reinforcement should be weighted
by colony quality and by the strength of evidence that the colony actually
succeeded.

The recent Wave 36 governance hardening matters here: `ColonyOutcome` is now
trustworthy enough to drive stronger reinforcement because solved coding tasks
are no longer systematically mislabeled as failures.

#### Current seam

The existing update happens in
[src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py),
where accessed entries receive:

- `alpha += 1` on success,
- `beta += 1` on failure,
- plus decay and mastery-restoration logic.

#### Concrete code changes

Primary files:

- [src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py)
- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- optionally
  [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
  to surface reinforcement drift diagnostics

Recommended update:

- replace constant `+1` updates with clipped quality-aware deltas:

  `delta_alpha = clip(0.5 + quality_score, 0.5, 1.5)`
  `delta_beta  = clip(0.5 + failure_penalty, 0.5, 1.5)`

- optionally weight by access mode:
  - `context_injection` gets full credit,
  - `tool_detail` gets medium credit,
  - `tool_search` gets weaker credit unless later reused.

- optionally add a bonus when:
  - the colony had verified successful `code_execute`,
  - or extracted knowledge entries after using the source trace.

Again: no new event types are required. `MemoryConfidenceUpdated` already
records arbitrary old/new alpha and beta.

#### Expected improvement

- better calibration between actual usefulness and future retrieval rank,
- stronger discrimination between "merely present" and "materially useful"
  knowledge,
- faster emergence of domain-specialized trace quality.

#### How to measure it

- calibration of retrieved-entry usefulness vs posterior mean,
- retrieval hit quality on subsequent colonies,
- Brier-like score on whether high-confidence entries actually help successful
  colonies,
- reduction in top-k entries with repeated negative feedback.

#### Risks

- runaway reinforcement loops,
- rich-get-richer bias,
- under-reinforcement of exploratory entries that were useful but not central.

#### Mitigation

- clip deltas,
- keep Thompson sampling,
- preserve priors and decay,
- monitor concentration growth (`alpha + beta`) per domain.

#### Precedent

- global reinforcement by best or good ants in ACO [1][2][3],
- rank-based reinforcement variants in the ACO family.

#### Priority

High impact, low effort. This is the closest thing to "closing the ACO loop"
without new contracts.

### 4.3 Proposal C: Adaptive evaporation per domain

#### Thesis

The current three-class decay system is good, but too coarse for a mature
knowledge economy. Different domains should learn different evaporation
behaviors from actual usage patterns.

The important point is not to replace `decay_class`, but to tune it.

#### Concrete code changes

Primary files:

- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [src/formicos/surface/memory_store.py](/c:/Users/User/FormicOSa/src/formicos/surface/memory_store.py)
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)
- workspace config surfaces already using `WorkspaceConfigChanged`

Recommended path:

1. Keep the existing class-level defaults.
2. Add a derived, workspace-level optional override map, for example:

   `domain_decay_overrides = { "python.testing": 0.997, "api.docs": 0.985 }`

3. Infer candidate overrides from:
   - prediction error accumulation,
   - successful reuse half-life,
   - frequency of refresh colonies,
   - positive vs negative `knowledge_feedback`,
   - outcome-weighted entry reuse.
4. Surface these as Queen suggestions first, not automatic tuning.

This can be implemented through existing workspace config change flows. No new
event types are necessary.

#### Expected improvement

- lower stale-knowledge influence in fast-moving domains,
- higher retention of durable patterns in stable domains,
- reduced maintenance churn,
- better retrieval precision over long horizons.

#### How to measure it

- prediction-error trend per domain,
- percentage of stale entries in top-k,
- rate of maintenance-triggered refresh per domain,
- downstream colony success after domain-specific tuning.

#### Risks

- oscillatory tuning,
- misclassifying domains from sparse evidence,
- making the system harder to reason about if overrides proliferate.

#### Mitigation

- start recommendation-only,
- require a minimum evidence threshold,
- decay overrides back toward defaults if evidence weakens.

#### Precedent

- adaptive evaporation work in dynamic ACO, especially the intuition from
  Mavrovouniotis and Yang that dynamic environments benefit from context-aware
  forgetting [12].

#### Priority

Medium-high impact, medium effort.

### 4.4 Proposal D: Stigmergic colony-configuration suggestions

#### Thesis

The Queen should keep authority over task decomposition and operator-facing
decisions, but the environment can help by suggesting likely-effective colony
shapes from past outcomes.

This is not "remove the Queen." It is "let the environment offer paths of least
resistance."

#### Concrete code changes

Primary files:

- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)
- optionally
  [src/formicos/surface/queen_tools.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_tools.py)
  for surfaced advisory tooling

Recommended path:

1. Aggregate `ColonyOutcome` by:
   - domain,
   - strategy,
   - caste mix,
   - successful tool-use profile,
   - token/cost efficiency.
2. Produce recommendation summaries such as:
   - "for python-testing tasks in this workspace, one coder plus one reviewer
     with sequential strategy has the best quality/cost ratio over the last 30
     days."
3. Inject these as advisory cues into the Queen briefing or as a surfaced config
   suggestion panel.

No new event types are needed. The substrate already exists in
`ProjectionStore.colony_outcomes`.

#### Expected improvement

- faster first-pass colony selection,
- lower wasted experimentation cost,
- more explainable topology/config choices,
- better use of accumulated local experience.

#### How to measure it

- first-try success rate,
- change in cost per successful colony,
- operator acceptance rate for suggestions,
- diversity of chosen colony configurations over time.

#### Risks

- overfitting to local data,
- suppressing exploration too early,
- reinforcing past suboptimal habits.

#### Mitigation

- make it advisory, not automatic,
- surface confidence and sample size,
- use Thompson-style exploration over candidate configurations later if the
  system matures.

#### Precedent

- G-Designer's task-adaptive topology recommendation framing [13],
- path preference and exploitation of successful routes in ACO [1][2][3].

#### Priority

Medium-high impact, low-medium effort.

### 4.5 Proposal E: Cross-colony trace inheritance

#### Thesis

When a colony is clearly a continuation or fusion of prior colony work, it
should inherit a softened version of parent pheromone topology rather than
starting from a neutral graph every time.

This is the route-level analogue of reusing knowledge entries.

#### Concrete code changes

Primary files:

- [src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)

Recommended path:

1. When a new colony is spawned from:
   - workflow continuation,
   - explicit merge/input sources,
   - or a thread with a clearly adjacent task,
   gather recent parent `pheromone_weights`.
2. Normalize and blend them:

   `w_child = clip(1.0 + lambda * mean(w_parent - 1.0), 0.1, 2.0)`

3. Use this as the child colony's initial `pheromone_weights`.

This does not require a new event type if treated as runtime initialization from
existing projections and spawn context.

#### Expected improvement

- fewer setup rounds in continuation tasks,
- smoother behavior on follow-up coding or review colonies,
- better reuse of successful team interaction motifs.

#### How to measure it

- rounds-to-first-useful-output for continuation colonies,
- token cost reduction on thread continuations,
- quality improvement vs neutral-initialization baseline.

#### Risks

- negative transfer from adjacent but meaningfully different tasks,
- over-carrying routing patterns that were only locally optimal,
- making colony behavior less legible if inheritance is implicit.

#### Mitigation

- only inherit from high-quality parents,
- decay inherited weights toward neutral,
- surface inheritance in colony detail/debug metadata.

#### Precedent

- transfer and reuse ideas in dynamic optimization versions of ACO,
- multi-scale construction analogies from biological stigmergy [7].

#### Priority

Medium impact, medium effort.

### 4.6 Proposal F: Lambda-branching-style stagnation diagnostics

#### Thesis

FormicOS should detect not only failed colonies, but shrinking search breadth in
both topology and knowledge layers. A branching-factor style metric is the right
tool for that.

#### Concrete code changes

Primary files:

- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- optionally
  [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)

Recommended metrics:

1. **Topology branching factor**:
   effective number of active incoming edges per agent, or entropy over
   normalized edge weights.
2. **Knowledge branching factor**:
   entropy or effective count over top-k retrieval posterior mass.
3. **Configuration branching factor**:
   diversity of successful strategy/caste selections over a moving window.

Generate an insight when:

- branching is low,
- failures or warnings are rising,
- and the same entries or same configurations dominate recent successful and
  failed work alike.

No new events are required if this remains a read-model diagnostic.

#### Expected improvement

- earlier detection of premature convergence,
- better timing for diversification or maintenance interventions,
- cleaner operator explanation of why the system appears "stuck."

#### How to measure it

- correlation between low branching and subsequent colony failure,
- reduction in repeated same-domain failures after interventions,
- change in recovery time after stagnation.

#### Risks

- false positives in domains that legitimately converge to one best pattern,
- alert fatigue.

#### Mitigation

- gate on both low branching and worsening outcomes,
- use it as `attention` or `info` before promoting it to automatic action.

#### Precedent

- stagnation diagnostics in MMAS and broader ACO literature [3][5].

#### Priority

Medium impact, low effort.

### 4.7 Prioritization summary

| Proposal | Impact | Effort | New event types? | Recommended timing |
|---|---|---:|---|---|
| A. Knowledge-weighted topology init | High | Medium | No | Wave 37 core |
| B. Outcome-weighted reinforcement | High | Low | No | Wave 37 core |
| C. Adaptive domain evaporation | Medium-high | Medium | No | Wave 37 core/advisory |
| D. Config suggestions from outcomes | Medium-high | Low-medium | No | Wave 37 core |
| E. Cross-colony trace inheritance | Medium | Medium | No | Wave 37.5 or later |
| F. Branching-factor diagnostics | Medium | Low | No | Wave 37 core |

If only three items ship first, they should be A, B, and F. Together they close
the loop:

- knowledge informs routing,
- outcomes reinforce knowledge,
- stagnation is monitored across both layers.

### 4.8 What can ship now without contract changes, and what should wait

Because FormicOS is event-sourced and the `core/` layer is intentionally stable,
it is worth separating "valuable" from "worth changing the object model for."

#### Can ship now without new event types

These are the proposals that fit cleanly into current surface/engine seams:

- Proposal A: knowledge-weighted topology initialization
- Proposal B: outcome-weighted knowledge reinforcement
- Proposal C: adaptive domain evaporation via derived config suggestions
- Proposal D: colony-configuration suggestions from `ColonyOutcome`
- Proposal F: branching-factor diagnostics

Proposal E can also ship without new event types if implemented as runtime
initialization from current projections and spawn context, rather than as a
newly persisted colony field.

#### Probably should not change contracts yet

There are two tempting directions that should wait until the cheaper work above
has been measured.

1. **Explicit completion tools for all agent types**.
   This is valuable, and the code-execution completion signal shows the general
   direction. But it is not necessary to prove the two-layer stigmergy thesis.
   It is better treated as a broader governance/completion architecture change.

2. **Persisted topology-trace provenance**.
   One could imagine new event payloads that explicitly record which knowledge
   priors or parent topologies seeded a colony's initial graph. That would make
   some analyses more replay-transparent, but it is not yet justified. The
   simpler question is whether the bias improves outcomes at all.

That distinction matters for planning discipline. FormicOS should first exploit
the unusually rich stigmergic substrate it already has. Only after that should
it consider widening the contract surface.

---

## 5. What Not To Do

### 5.1 Do not interpret "stigmergy" as a reason to remove explicit governance

Pure stigmergic systems work best with many simple agents and cheap actions. LLM
agents are neither simple nor cheap. Cognitive stigmergy work already
recognized that software agents can be richer than insects and that
artifact-mediated coordination must be adapted accordingly [15].

FormicOS's Queen is not anti-stigmergic. It is a necessary sparse-governance
layer for expensive, semantically overpowered agents.

### 5.2 Do not expect pure stigmergy to dominate in very small teams

The density-threshold result the prompt cited is directionally important.
Khushiyant et al.'s 2025 preprint on stigmergic communication for scalable
multi-agent reinforcement learning argues for a critical density around
`rho_c ~= 0.230`, below which internal memory dominates and above which
stigmergic coordination becomes advantageous [16]. Because this is a preprint,
it should be treated as suggestive rather than settled.

But the intuition fits FormicOS well:

- 1-3 agent tasks often do not need environmental coordination,
- the fixed overhead of trace mediation is not free,
- the payoff appears when task decomposition, concurrency, or fault tolerance
  matter.

That argues against overusing stigmergic machinery for small, tightly scoped
jobs.

### 5.3 Do not force stigmergy into real-time synchronization problems

Stigmergic coordination is trace-based, asynchronous, and indirect. That is
exactly why it scales well in some settings. It is also why it is a bad fit for
low-latency, strongly synchronized tasks.

If a task needs:

- sub-second coordination,
- precise simultaneous agreement,
- or continuous shared world-state coherence,

then direct protocol design is usually superior to environmental trace updates.

FormicOS should therefore avoid selling the knowledge substrate as a universal
coordination answer. It is strongest when delayed environmental influence is an
advantage, not when it is a liability.

### 5.4 Do not let environment corruption become a silent failure mode

Self-organizing systems are uniquely vulnerable to environmental corruption
because the environment is itself the coordination channel. Di Marzo Serugendo's
dependability framing is relevant here: abnormal environmental conditions can
propagate system-wide if the system relies on local cues for global order [17].

For FormicOS, "environment corruption" means:

- stale or contradictory high-confidence entries,
- runaway co-occurrence reinforcement,
- bad federation inputs with insufficient trust discounting,
- inaccurate outcome labeling,
- or maintenance routines that over-promote the wrong traces.

This is not a minor data-quality issue. It is the equivalent of poisoning the
pheromone field.

That is why the following are non-negotiable:

- truthful outcome labeling,
- confidence updates tied to real success/failure,
- contradiction detection,
- maintenance budgets,
- and trust-aware federation.

### 5.5 Do not assume "simple rules -> complex behavior" transfers cleanly to LLM agents

Insect stigmergy assumes simple local agents whose behavior is mostly in the
environmental coupling. LLM agents are already complex, reflective, and
linguistically expressive. Their failure modes are therefore different:

- rhetorical self-consistency can masquerade as convergence,
- local verbosity can overwhelm subtle environmental signals,
- and agents can "reason around" heuristics rather than just respond to them.

That means FormicOS should prefer **small, deterministic stigmergic signals**
that shape agent opportunity structures, not giant emergent systems that assume
the agents themselves will stay behaviorally simple.

### 5.6 Do not over-automate configuration choice from sparse local data

Once the environment starts recommending colony shapes or topology biases, it
will be tempting to make those recommendations automatic. That is premature.

The right sequence is:

1. observe,
2. recommend,
3. measure,
4. only then automate narrow cases.

Otherwise the system risks building a local optimum and calling it learning.

---

## 6. Benchmarking Strategy

If stigmergic improvements are going to matter architecturally, they need a
measurement plan that covers more than final benchmark score.

### 6.1 What to compare against

Two external comparison points are especially relevant.

- **DyTopo** reports average improvements over the strongest baseline of about
  `+6.2` points and about `48%` fewer output tokens while dynamically routing
  agent communication via semantic matching [14]. This is the clearest
  comparison target for Layer 1.
- **G-Designer** reports adaptive topology selection with up to `95.33%` token
  reduction on HumanEval while preserving or improving task performance across
  six benchmarks [13]. This is the clearest comparison target for
  task-adaptive topology and communication efficiency.

Both are about topology. FormicOS should not try to beat them only on topology.
Its distinctive claim is that topology plus long-run knowledge stigmergy should
outperform topology-only systems on repeated-domain work, long-horizon system
health, and operator-guided adaptation.

### 6.2 What success should mean for FormicOS

The right evaluation stack is four-layered.

#### Task outcome

- pass@1 / pass@k on HumanEval,
- resolution rate on SWE-bench slices,
- answer accuracy on MATH / GAIA,
- artifact contract satisfaction for FormicOS-native tasks.

#### Colony efficiency

- total rounds,
- tokens in/out,
- cost per successful colony,
- time to first successful tool use,
- time to final completion.

#### Substrate quality

- retrieval diversity,
- posterior calibration vs actual usefulness,
- branching-factor metrics,
- contradiction rate,
- maintenance spend,
- knowledge pulse health over time.

#### Operator trust

- percentage of visibly successful colonies marked successful,
- percentage of successful suggestions accepted,
- proportion of outcome badges that match operator judgment.

This fourth layer is easy to forget and critical. A stigmergic substrate that
improves pass@1 but routinely mislabels success or hides its reasoning will
still damage adoption.

### 6.3 What tasks should benefit most

The best candidates are tasks with the following properties:

- decomposable into semi-independent subtasks,
- repeated enough for environmental traces to accumulate,
- domain reuse across colonies,
- meaningful cost pressure,
- tolerance for asynchronous indirect coordination.

Concretely:

- coding tasks with stable local patterns and repeated libraries,
- review and repair loops,
- documentation + implementation pairs,
- research synthesis over recurring domains,
- maintenance workflows over the same knowledge regions.

### 6.4 What tasks should not use stigmergy heavily

Avoid over-indexing on stigmergy for:

- 1-3 agent tasks with clear single-owner execution,
- strongly real-time tasks,
- tasks requiring consistent global optimization every step,
- one-off tasks in domains with no reusable substrate,
- tasks where environmental corruption cost is high and evidence is sparse.

These should stay Queen-heavy and direct.

### 6.5 Recommended benchmark suites

#### HumanEval

Why:

- sensitive to code generation correctness,
- easy to measure repeated-domain improvements,
- aligns with code-execution-based completion signals.

Use:

- compare current Wave 36 baseline against
  knowledge-weighted topology initialization and
  outcome-weighted reinforcement.

#### SWE-bench

Why:

- exposes long-horizon coding and repair behavior,
- has recurring repository patterns where environmental memory should matter,
- useful for continuation-colony and trace-inheritance evaluation.

Use:

- measure fewer warmup rounds and lower cost on follow-up issue clusters.

#### GAIA

Why:

- multi-step tool use and information gathering,
- tests whether stigmergic signals help outside pure coding.

Use:

- stress whether the knowledge layer improves coordination in mixed tool-use
  settings.

#### MATH

Why:

- useful to benchmark DyTopo-style topology effects,
- but weaker fit for the knowledge substrate because domain reuse is lower.

Use:

- mostly as a control to see when topology helps more than environmental memory.

### 6.6 Experimental matrix

Recommended ablation stack:

1. sequential baseline
2. current Wave 36 DyTopo + current knowledge substrate
3. + Proposal A (knowledge-weighted topology init)
4. + Proposal B (outcome-weighted reinforcement)
5. + Proposal F (branching diagnostics and diversification triggers)
6. + Proposal C (adaptive decay)
7. + Proposal D (config suggestions)

This matters because FormicOS's claim is compositional. The expected gain is not
from one isolated trick but from coupling a topology layer with a persistent,
probabilistic environment.

### 6.7 FormicOS-native benchmark ideas

External benchmarks are necessary but insufficient. FormicOS should also measure
what outside papers cannot:

- repeated-domain colony performance over 30-day windows,
- knowledge pulse health under continuous use,
- maintenance dispatch precision,
- federation usefulness under trust discounting,
- and operator-visible truthfulness of colony outcomes.

That is where the architecture should eventually beat topology-only systems.

---

## 7. Recommended Wave 37 Direction

This memo is not a Wave 37 plan, but it should end with an architecture
preference.

### 7.1 The central decision

Treat the knowledge system as the **primary long-term stigmergic substrate** and
treat the topology layer as the **short-term routing adaptation layer**.

Do not attempt to unify them into one score.

### 7.2 The recommended sequence

1. Strengthen the existing outcome -> knowledge loop.
2. Let knowledge bias topology initialization.
3. Add branching diagnostics so the system knows when its pheromone field is
   getting too narrow.
4. Use accumulated outcomes to advise colony configuration.
5. Only later consider more explicit completion tools or broader non-code
   verification signals as part of a general environmental feedback expansion.

### 7.3 Why this sequence is right

It uses what FormicOS has already solved:

- replay-derived outcomes,
- truthful success labeling for coding colonies,
- posterior knowledge confidence,
- maintenance and insight infrastructure,
- and a live topology layer.

It also respects the repo's architectural constraints:

- no core-layer churn,
- no required new event types,
- no need to rewrite the Queen,
- no need to replace the knowledge system with a different abstraction.

### 7.4 The strongest claim FormicOS can honestly make

Not:

"We have multi-agent memory."

But:

"We have a self-maintaining, confidence-calibrated environmental trace field
that lets colonies coordinate indirectly across time, and a topology layer that
lets agents coordinate indirectly within a task."

That is a much stronger systems thesis, and it is consistent with both the code
and the literature.

---

## References

[1] Marco Dorigo, Gianni Di Caro, and Luca M. Gambardella. "Ant Algorithms for
Discrete Optimization." *Artificial Life*, 5(2), 1999.
https://ieeexplore.ieee.org/document/6787854/

[2] Marco Dorigo and Luca M. Gambardella. "Ant Colony System: A Cooperative
Learning Approach to the Traveling Salesman Problem." *IEEE Transactions on
Evolutionary Computation*, 1(1), 1997.
https://doi.org/10.1109/4235.585892

[3] Thomas Stutzle and Holger H. Hoos. "MAX-MIN Ant System." *Future
Generation Computer Systems*, 16(8), 2000, pp. 889-914.
https://doi.org/10.1016/S0167-739X(00)00043-1

[4] Walter J. Gutjahr. "ACO Algorithms with Guaranteed Convergence to the
Optimal Solution." *Information Processing Letters*, 82(3), 2002, pp. 145-153.
https://doi.org/10.1016/S0020-0190(01)00258-7

[5] Walter J. Gutjahr. "A Graph-Based Ant System and Its Convergence."
*Future Generation Computer Systems*, 16(8), 2000, pp. 873-888.
Table of contents reference:
https://ftp.math.utah.edu/pub/tex/bib/toc/futgencompsys.html

[6] Guy Theraulaz and Eric Bonabeau. "A Brief History of Stigmergy."
*Artificial Life*, 5(2), 1999, pp. 97-116.
https://www.santafe.edu/research/results/papers/1112-a-brief-history-of-stigmergy

[7] Guy Theraulaz, Eric Bonabeau, and colleagues. "The Origin of Nest
Complexity in Social Insects." *Proceedings of the National Academy of
Sciences*, 95(23), 1998.
https://www.pnas.org/doi/10.1073/pnas.95.23.13058

[8] H. Van Dyke Parunak. "A Survey of Environments and Mechanisms for
Human-Human Stigmergy." In *Environments for Multi-Agent Systems II*, LNAI 3830,
Springer, 2006, pp. 163-186.
Index reference:
https://garfield.library.upenn.edu/histcomp/bush_atlantic-monthly/index-tl-15.html

[9] FoundationAgents. "MetaGPT: The Multi-Agent Framework." Project repository
and public documentation, accessed March 2026.
https://github.com/FoundationAgents/MetaGPT
https://docs.deepwisdom.ai/

[10] LangChain. "LangGraph" official documentation on stateful graphs,
subgraphs, and persistence, accessed March 2026.
https://docs.langchain.com/oss/python/langgraph/use-subgraphs

[11] CrewAI. Official documentation on crews and memory utilization, accessed
March 2026.
https://docs.crewai.com/en/concepts/crews

[12] Michalis Mavrovouniotis and Shengxiang Yang. "Elitism-Based Immigrants for
Ant Colony Optimization in Dynamic Environments: Adapting the Replacement
Rate." Conference paper, 2014.
Repository record:
https://www.openarchives.gr/aggregator-openarchives/edm/ktisis/000029-20.500.14279_30857

[13] Guibin Zhang, Yanwei Yue, Xiangguo Sun, Guancheng Wan, Miao Yu, Junfeng
Fang, Kun Wang, Tianlong Chen, and Dawei Cheng. "G-Designer: Architecting
Multi-agent Communication Topologies via Graph Neural Networks." *Proceedings of
the 42nd International Conference on Machine Learning (ICML)*, PMLR 267, 2025.
https://proceedings.mlr.press/v267/zhang25cu.html

[14] Yuxing Lu, Yucheng Hu, Xukai Zhao, and Jiuxin Cao. "DyTopo: Dynamic
Topology Routing for Multi-Agent Reasoning via Semantic Matching." arXiv
preprint, 2026.
CatalyzeX summary and arXiv-linked entry:
https://www.catalyzex.com/paper/dytopo-dynamic-topology-routing-for-multi

[15] Alessandro Ricci, Andrea Omicini, and Mirko Viroli. "Cognitive Stigmergy:
Towards a Framework Based on Agents and Artifacts." In the agents/artifacts
coordination literature; see also:
https://cris.unibo.it/handle/11585/31257

[16] Khushiyant et al. "Emergent Collective Memory in Decentralized Multi-Agent
AI Systems." arXiv preprint, 2025. Treat the density-threshold claim as
suggestive until independently replicated.
https://arxiv.org/abs/2512.10166

[17] Giovanna Di Marzo Serugendo. "Robustness and Dependability of
Self-Organizing Systems - A Safety Engineering Perspective." In *Proceedings of
the 11th International Symposium on Stabilization, Safety, and Security of
Distributed Systems*, 2009.
Citation listing:
https://backend.orbit.dtu.dk/ws/portalfiles/portal/92351644/emas_14_informal_proc.pdf
