# Wave 52: Intelligence Findings

**Date:** 2026-03-20

Findings from the default-intelligence audit, ordered by severity.

---

## Already Excellent

Before listing gaps, these are real strengths that should not be
underestimated or disrupted:

1. **The learning loop is real.** Every colony updates Bayesian
   confidence, co-occurrence weights, and knowledge coverage. Thompson
   Sampling retrieval means the system genuinely improves with use.
   This is not aspirational -- it is event-sourced and active.

2. **Proactive intelligence is deterministic and fast.** 14 rules run
   in <100ms with no LLM calls. Contradiction detection, coverage gaps,
   strategy efficiency, cost outliers, and earned autonomy all work.

3. **The Queen is genuinely well-briefed.** Every Queen response gets
   automatically enriched with knowledge retrieval, briefing insights,
   thread context, decay recommendations, config recommendations,
   and metacognitive nudges. No configuration required.

4. **Reactive foraging is wired end-to-end.** When retrieval confidence
   is low (top score < 0.35), background foraging triggers automatically.
   Results enter the knowledge store as candidates with conservative
   priors. This is a real closed loop.

5. **Post-colony hooks are comprehensive.** Memory extraction, transcript
   harvest, confidence update, co-occurrence reinforcement, and
   auto-template creation all fire automatically after every colony.
   The system learns from every task without operator intervention.

6. **Credential scanning is built into the knowledge pipeline.** 5-axis
   security scanning runs on every extracted entry. This is a real
   safety substrate, not a checkbox.

---

## Findings

### F1: A2A and AG-UI bypass workspace intelligence at intake (HIGH)

**What:** The A2A path uses template tag matching and keyword
classification for routing. AG-UI uses only hardcoded defaults. Neither
path consults workspace knowledge, colony outcomes, learned templates,
or proactive intelligence before spawning.

**Why it matters:** External integrators -- the callers most likely to
be automated and high-volume -- get the least intelligent defaults.
The system's compounding knowledge improves retrieval *during* execution
but never improves *routing* for these paths.

**Concrete gap:** An A2A caller submitting their 100th task to a
workspace with rich knowledge, proven templates, and clear outcome
patterns gets the same generic coder+reviewer/stigmergic/10-round
defaults as their 1st task.

**Bounded fix:** Before spawning from A2A/AG-UI, consult the workspace's
learned templates and outcome-derived config recommendations. Use the
existing `task_classifier` + `template_manager` + config recommendation
infrastructure. No new substrate needed -- just wiring.

### F2: Learned templates are captured but never auto-applied (MEDIUM)

**What:** `_hook_auto_template` creates learned templates from quality
colonies (>= 0.7 quality, >= 3 rounds, Queen-spawned). These appear in
`list_templates` and `preview-colony` with success/failure counts. But
no path auto-substitutes learned template parameters for default
parameters.

**Why it matters:** The system captures what worked but does not use it
unless the Queen (or operator) explicitly calls `list_templates` and
chooses the template. The learning exists but does not compound
automatically.

**Concrete gap:** After 5 successful Python implementation colonies all
using coder+reviewer/stigmergic/10-rounds, the system has a learned
template proving this works. But the next Python task still requires
the Queen to manually discover and select it.

**Bounded fix:** In the A2A `_select_team()` flow, after tag matching
and before classifier fallback, check for a learned template matching
the classified category with success_count > 0. Use its parameters
instead of classifier defaults. For Queen path, include matched learned
template info in the briefing so the Queen sees it without calling
`list_templates`.

### F3: Colony outcome history not in Queen briefing (MEDIUM)

**What:** Colony outcomes feed into 4 performance rules (strategy
efficiency, diminishing rounds, cost outlier, knowledge ROI), and
those rules appear in the briefing. But the actual outcome history
(which strategies worked, which failed, at what cost) is only
available if the Queen calls `inspect_colony` per colony.

**Why it matters:** The Queen sees derived insights ("stigmergic
strategy has higher quality scores") but not the evidence ("last 5
stigmergic colonies: 0.8, 0.9, 0.7, 0.85, 0.9 quality"). This makes
the Queen's decisions less grounded and harder to explain to the
operator.

**Concrete gap:** Performance rules may recommend strategy changes,
but the Queen cannot reference specific prior results without
additional tool calls. This makes the recommendation feel arbitrary
to operators.

**Bounded fix:** Add a compact outcome summary to the briefing
assembly -- e.g., last 5 colony outcomes with strategy, quality, cost.
Data already exists in projections; this is a formatting change in
`queen_runtime.py` briefing injection.

### F4: External budget truth is inconsistent, and AG-UI is the clearest gap (MEDIUM)

**What:** A2A passes a per-colony `budget_limit` from template/classifier
selection, but it still does not use the Queen-style workspace spawn gate.
AG-UI does neither: it passes no `budget_limit`, so it silently inherits the
runtime default of `5.0`, and it also skips the workspace spawn gate.

**Why it matters:** External callers do not get one clear budget contract.
A2A has explicit per-colony limits, AG-UI gets a silent server default, and
neither external path uses the same workspace-level guardrail the Queen path uses.

**Bounded fix:** At minimum, remove AG-UI's silent `5.0` default and make its
budget behavior explicit. If Wave 52 keeps full parity in scope, add the same
workspace spawn gate to both external paths.

### F5: Task classifier results invisible to Queen (LOW)

**What:** When the Queen spawns a colony, `task_classifier.classify_task()`
runs internally to set default parameters if the Queen doesn't specify
them. But the classification result is never shown to the Queen in the
briefing or as a tool response.

**Why it matters:** The Queen makes routing decisions without seeing how
the system would classify the task. If the classifier suggests
"research" but the Queen defaults to "code_implementation" castes,
there's no signal that the decision diverged from the system's analysis.

**Bounded fix:** Include task classification in the `spawn_colony` tool
response (e.g., "System classified this as: research. You chose:
coder+reviewer."). No briefing change needed -- just response
enrichment.

### F6: Config recommendations require manual tool interaction (LOW)

**What:** Configuration recommendations appear in the Queen briefing
(recommended strategy, caste composition, rounds, model tiers with
evidence). But applying a recommendation requires the Queen to call
`suggest_config_change` to create a proposal, then `approve_config_change`
to apply it. The proposal has a 5-minute TTL.

**Why it matters:** Good recommendations are surfaced but applying them
is a multi-step process. The Queen may see "stigmergic strategy has
higher quality" in every briefing but never act on it because the
application path requires multiple tool calls.

**Not a fix target for Wave 52:** This is intentional governance (config
changes require operator awareness). Document it as a design choice,
not a bug. The friction is the feature.

### F7: Distillation candidates not surfaced in briefing (LOW)

**What:** Dense co-occurrence clusters (>= 5 entries, avg weight > 3.0)
are flagged as distillation candidates during maintenance. When policy
allows, archivist colonies synthesize them. But the candidates are not
visible in the Queen briefing -- they're only in projection state.

**Why it matters:** The Queen cannot proactively mention "you have 3
knowledge clusters ready for distillation" to the operator. Distillation
happens silently in maintenance or not at all.

**Bounded fix:** Add a distillation-candidate count to the briefing
when count > 0. One line, no new rule needed.

---

## Disconnected Intelligence (Summary)

| Intelligence Feature      | Exists | Connected to Default Path? | Gap |
|---------------------------|:------:|:--------------------------:|-----|
| Knowledge retrieval       |  YES   |    Queen only              | A2A/AG-UI skip pre-spawn |
| Proactive briefing        |  YES   |    Queen only              | Not available to integrators |
| Learned templates         |  YES   |    Display only            | Never auto-substituted |
| Colony outcomes           |  YES   |    Rules only              | Raw history not in briefing |
| Task classification       |  YES   |    Internal only           | Invisible to Queen |
| Config recommendations    |  YES   |    Briefing only           | Multi-step application (intentional) |
| Distillation candidates   |  YES   |    Projection only         | Not in briefing |
| Reactive foraging         |  YES   |    Fully connected         | No gap |
| Confidence evolution      |  YES   |    Fully connected         | No gap |
| Co-occurrence weights     |  YES   |    Fully connected         | No gap |
| Transcript harvest        |  YES   |    Fully connected         | No gap |
| Auto-template capture     |  YES   |    Fully connected         | Capture works, application doesn't |

---

## Top 3 Seams That Reduce Perceived Intelligence

1. **A2A/AG-UI intake blindness (F1).** External callers never benefit
   from the workspace's accumulated intelligence for routing decisions.
   The system looks static to integrators even when internally it has
   rich learning.

2. **Learned template capture-without-application (F2).** The system
   proves what works but does not use it. This is the most visible gap
   between "the codebase is intelligent" and "the product feels
   intelligent."

3. **Colony outcome opacity in briefing (F3).** The Queen sees
   recommendations but not evidence. This makes the Queen's decisions
   less grounded and harder for operators to trust.

---

## Defaults That Should Be Unified Before New Capability

1. **Pre-spawn knowledge consultation.** The infrastructure exists
   (fetch_knowledge_for_colony, task_classifier, template_manager,
   config recommendations). Wire it into A2A and AG-UI intake before
   building new intelligence features.

2. **Learned template application.** The capture pipeline is solid.
   Add a matching step in A2A `_select_team()` and surface matched
   templates in the Queen briefing. This turns captured learning into
   active routing improvement.

3. **Budget truth parity.** AG-UI should stop silently inheriting `5.0`, and
   external paths should move closer to the Queen's spawn-gate behavior.

---

## Wave 52 Polish Recommendations

### Should polish (bounded, high impact)

- **Wire learned templates into A2A routing** -- check learned templates
  after tag match, before classifier fallback
- **Add compact outcome summary to Queen briefing** -- last N colony
  outcomes with strategy/quality/cost
- **Make AG-UI budget behavior explicit; add spawn-gate parity if it stays bounded**
- **Surface learned template match in Queen briefing** -- if a learned
  template matches the current task category, mention it

### Should leave alone

- **Config recommendation application friction** -- intentional
  governance; the multi-step process is the feature
- **Queen intelligence concentration** -- the Queen is the primary
  interface and should stay the most intelligent path; the fix is
  bringing non-Queen paths closer, not redistributing Queen intelligence
- **Classifier keyword heuristics** -- deterministic classification is
  correct for this system; LLM-based classification would add latency
  and unpredictability
- **Template auto-substitution in Queen path** -- the Queen should
  decide, not the system; surface the match, don't force it

---

## Final Answers

**Is FormicOS actually intelligent out of the box today?**

Yes. The Queen Chat path is genuinely intelligent by default. The
learning loop is real, event-sourced, and Bayesian. Every colony teaches
the system something, and retrieval quality demonstrably improves with
use. Proactive intelligence runs deterministically and surfaces real
insights. Reactive foraging closes knowledge gaps automatically. The
substrate is not aspirational -- it is shipped and active.

The gap is not intelligence; it is *reach*. The intelligence concentrates
in the Queen Chat path. Non-Queen paths contribute to learning but do
not benefit from it at intake time.

**Which 3 seams most reduce that feeling?**

1. A2A/AG-UI intake ignores workspace learning (static defaults)
2. Learned templates captured but never auto-applied (learning without compounding)
3. Colony outcome evidence not in Queen briefing (recommendations without grounding)

**Which defaults should be unified before new capability expansion?**

Pre-spawn intelligence consultation (knowledge + templates + outcomes)
should reach A2A and AG-UI paths. Budget behavior should be explicit,
and external spawn-gate behavior should be consistent if it stays in scope.
These use existing infrastructure -- the work is wiring, not invention.

**What should Wave 52 polish, and what should it leave alone?**

Polish: learned template routing in A2A, outcome summary in briefing,
AG-UI budget truth, optional external spawn-gate parity, learned template surfacing in briefing.

Leave alone: config recommendation friction, classifier heuristics,
Queen intelligence concentration, template auto-substitution in Queen path.
