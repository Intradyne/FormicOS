# Architecture Analysis Report Template

**Run ID:** _(from manifest)_
**Date:**
**Commit:**
**Analyst:**

---

## 1. System Under Test

Describe the exact configuration that produced the measured results.

### Components active

| Component | Version / State | Notes |
|-----------|----------------|-------|
| Core event union | 62 events | |
| Engine strategy | stigmergic / sequential | |
| Knowledge catalog | Thompson Sampling, 6-signal composite | |
| Forager | reactive / reactive+proactive / disabled | |
| Federation | enabled / disabled | |
| Sandbox | Docker-isolated / host | |
| Model(s) | _(from conditions.model_mix)_ | |

### What was NOT active

List subsystems that exist in code but were disabled or not exercised
during this measurement. Be explicit — readers should not assume a
capability was tested just because the code exists.

---

## 2. Knowledge Flow Analysis

Trace the knowledge lifecycle as it actually operated during the run.

### Extraction path

```
Colony completes round
  -> transcript harvest (hook 4.5)
  -> LLM extraction
  -> 5-axis security scan
  -> MemoryEntryCreated at candidate status
  -> admission scoring
  -> entry available for retrieval
```

Did this path fire for every colony? Were entries extracted? At what rate?

### Retrieval path

```
Colony starts round
  -> context assembly queries knowledge catalog
  -> 6-signal composite scoring
  -> tiered retrieval (summary -> standard -> full)
  -> entries injected into agent context
```

Did retrieval surface relevant entries? Was the access_ratio nonzero?

### Forager path (if active)

```
Retrieval detects gap (low-confidence results)
  -> ForageRequested emitted
  -> ForagerService runs bounded search
  -> EgressGateway enforces policy
  -> FetchPipeline extracts content
  -> ContentQuality scores
  -> Dedup check (SHA-256)
  -> MemoryEntryCreated with forager provenance
```

Did foraging trigger? How many cycles? Entries admitted vs rejected?

### Proactive path (if active)

```
Maintenance loop runs briefing
  -> proactive_intelligence detects gap/stale/decline
  -> forage_signal metadata emitted
  -> MaintenanceDispatcher evaluates
  -> ForagerService runs background cycle
```

Did proactive foraging trigger? From which rules?

---

## 3. Coordination Analysis

### Stigmergic routing (if used)

- Did pheromone weights converge or oscillate?
- Was adaptive evaporation triggered? How many stalls?
- Did the branching factor stay healthy (>= 2.0)?

### Colony lifecycle

| Metric | Value |
|--------|-------|
| Total colonies spawned | |
| Completed | |
| Failed | |
| Escalated | |
| Avg rounds per colony | |
| Avg cost per colony | |

### Parallel execution (if used)

- Were DelegationPlan DAGs used?
- How many parallel groups?
- Did dependencies cause bottlenecks?

---

## 4. What Worked

List specific architectural decisions that contributed positively to the
measured outcomes. Ground each claim in data from the run.

| Decision | Evidence | Contribution |
|----------|----------|--------------|
| | | |

---

## 5. What Did Not Work

List specific architectural weaknesses exposed by the run. Distinguish:
- **design limitation** — the architecture cannot support this
- **implementation gap** — the design is right but the code is incomplete
- **tuning debt** — the design works but parameters need adjustment

| Weakness | Category | Evidence | Suggested Fix |
|----------|----------|----------|---------------|
| | | | |

---

## 6. Honest Assessment

_(Two to three paragraphs. What does this run tell us about the
architecture? What would need to change for the next measurement to
be more conclusive?)_

Do not conflate "the architecture is sound" with "the numbers are good."
A sound architecture can produce flat numbers if the task suite does not
exercise knowledge transfer. A rising curve can mask architectural debt
if the tasks are too easy.
