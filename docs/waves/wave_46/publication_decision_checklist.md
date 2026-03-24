# Publication Decision Checklist

Use this checklist to decide whether measurement results warrant publication
and in what form. The checklist enforces honesty — it is designed to prevent
overclaiming, not to prevent publication.

---

## Prerequisite: Harness integrity

All of the following must be true before any publication decision:

- [ ] Clean-room isolation is implemented and verified (unique workspace per
      run, no cross-run contamination).
- [ ] `knowledge_used` and `knowledge_attribution` are populated from
      replay-safe access truth (via `_build_attribution()`).
- [ ] Run manifests contain commit hash, config hash, and all locked
      conditions.
- [ ] The run review checklist has been completed for every run included in
      the publication.

If any of these are false, stop. Fix the harness before publishing.

---

## Data sufficiency

### Minimum viable evidence

- [ ] At least one comparison pair exists: colony with knowledge vs colony
      without knowledge, on the same suite, same model, same conditions.
- [ ] At least the pilot suite (or larger) has been run to completion with
      no skipped tasks.
- [ ] The compounding-curve analysis template has been filled from real data.

### Statistical rigor (for stronger claims)

- [ ] At least 3 runs per config (for bootstrap 95% CIs).
- [ ] Paired-difference comparisons show significance (when multi-run
      analysis is implemented).
- [ ] The task suite has >= 20 tasks for breadth claims, or the claim is
      scoped to the tested domain.

### Forager contribution (if claiming foraging matters)

- [ ] A config comparison exists: knowledge+foraging vs knowledge-only.
- [ ] Forager-sourced entries are identifiable in `knowledge_used`
      attribution.
- [ ] At least some forager-sourced entries were accessed by later tasks.

---

## Publication form decision tree

### Path A: Rising curve with attribution

Evidence: quality trend is rising, knowledge_used shows cross-task transfer,
cost or time improves.

Publication options:
- [ ] Blog post with curves, attribution examples, and honest limitations
- [ ] Technical report with full methodology, conditions, and failure analysis
- [ ] Preprint (if statistical rigor thresholds are met)

### Path B: Mixed curve with domain-specific signal

Evidence: curve rises in some task clusters but not others. Knowledge
transfer is domain-dependent.

Publication options:
- [ ] Blog post focused on domains where compounding works, with honest
      characterization of where it does not
- [ ] Technical report analyzing which task properties predict knowledge
      transfer benefit

### Path C: Flat curve

Evidence: no measurable difference between knowledge and no-knowledge
configs, or curve is flat/declining.

Publication options:
- [ ] Honest failure analysis: what the architecture attempted, what was
      measured, why the curve was flat
- [ ] Technical report on the measurement methodology itself (harness
      design, clean-room isolation, attribution)
- [ ] Internal-only report with lessons for future development

All three paths are legitimate. The worst outcome is not publishing a flat
curve — it is publishing a rising curve that is not real.

---

## Content review

Before publishing any artifact:

- [ ] Every chart is generated from real run data, not hand-drawn or
      hypothetical.
- [ ] Every number is traceable to a specific run manifest.
- [ ] The methodology section describes locked conditions, knowledge mode,
      foraging state, and model mix.
- [ ] Limitations are stated prominently, not buried in footnotes.
- [ ] The product identity (editable shared brain, operator-visible traces)
      is ahead of the benchmark identity in framing.
- [ ] No benchmark-specific code path exists in product code.
- [ ] Cost is reported honestly alongside quality.
- [ ] Variance / confidence intervals are shown when multi-run data exists.

---

## Anti-patterns to avoid

- [ ] **NOT** claiming "publication-ready" when only a pilot exists
- [ ] **NOT** reporting best-of-N runs without stating N
- [ ] **NOT** omitting failed tasks from curves
- [ ] **NOT** comparing configs with different model mixes without disclosure
- [ ] **NOT** framing a benchmark score as the product thesis
- [ ] **NOT** using "statistically significant" without actual significance
      tests
- [ ] **NOT** showing cost only when it favors the system
