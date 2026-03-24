# Run Review Checklist

Use this checklist after every sequential eval run before drawing conclusions
or publishing results.

---

## Pre-run verification

- [ ] **Manifest exists.** `data/eval/sequential/{suite_id}/run_{timestamp}.json`
      contains a valid `conditions` block with all locked fields populated.
- [ ] **Config hash matches.** The `config_hash` in the manifest matches a
      recomputation from the current config. If it does not, the config drifted
      between runs.
- [ ] **Commit recorded.** The commit hash in the manifest (when implemented)
      matches the source tree that produced the run. If running from a dirty
      tree, note that explicitly.
- [ ] **Suite matches intent.** The `task_order` in conditions matches the
      suite YAML. Tasks were not reordered, added, or removed ad hoc.

## Isolation verification

- [ ] **Workspace identity.** Confirm the `workspace_id` in conditions. Was
      this a fresh workspace or a reused one?
- [ ] **Knowledge mode.** Was `knowledge_mode` set to `accumulate`, `empty`,
      or `snapshot`? Does this match the intended experiment?
- [ ] **No contamination.** If comparing configs, each config used its own
      workspace. Knowledge from one config's run did not leak into another.
- [ ] **Foraging state.** Was foraging enabled or disabled? If enabled, were
      there network issues that prevented it from functioning?

## Result integrity

- [ ] **All tasks ran.** The number of `TaskResult` entries matches the
      number of tasks in the suite. No tasks were skipped or timed out
      silently.
- [ ] **Status accuracy.** Failed tasks are marked `failed`, not `completed`
      with quality 0. Check that governance convergence detection is working.
- [ ] **Cost plausibility.** Total cost is within expected bounds for the
      model mix and task count. Flag outliers.
- [ ] **Quality plausibility.** Quality scores are within [0, 1]. Any score
      of exactly 0.0 or 1.0 should be inspected — perfect scores may indicate
      rubric issues.

## Knowledge verification

- [ ] **Entries extracted.** `entries_extracted` is nonzero for at least some
      tasks (unless the suite is designed to not produce knowledge).
- [ ] **Entries accessed.** `entries_accessed` is nonzero for later tasks
      (if `knowledge_mode` is `accumulate`). If zero, knowledge never
      transferred.
- [ ] **knowledge_used populated.** Entry IDs in `knowledge_used` (and
      the richer `knowledge_attribution.used` dicts) point to real entries.
      Spot-check at least one.
- [ ] **No phantom entries.** Accessed entries were actually created by
      earlier tasks in this run, not inherited from a prior run's workspace.

## Curve sanity

- [ ] **Trend computed.** `compute_curves()` ran without errors.
- [ ] **Trend direction checked.** The reported trend (rising/flat/declining)
      matches visual inspection of the raw curve.
- [ ] **First-half vs second-half is honest.** The trend computation splits
      at the midpoint. If the suite has an odd number of tasks, note which
      half gets the extra task.
- [ ] **Outlier influence.** A single very high or very low score should not
      dominate the trend conclusion. Note if one task drives the entire
      result.

## Comparison validity (if comparing configs)

- [ ] **Same suite.** Both configs used the same `suite_id` with the same
      `task_order`.
- [ ] **Same model mix.** Unless the comparison is specifically about model
      differences, `model_mix` should match.
- [ ] **Same budget.** `budget_per_task` and `max_rounds_per_task` should
      match unless that is the variable under test.
- [ ] **Sufficient runs.** _(When multi-run is implemented.)_ At least 3
      runs per config for bootstrap CIs. A single run comparison is
      anecdotal, not statistical.

## Reporting honesty

- [ ] **Claims match data.** Every claim in the analysis is traceable to a
      specific number in the run output.
- [ ] **Limitations stated.** The analysis notes: suite size, number of runs,
      whether knowledge_used was populated, whether foraging was active.
- [ ] **No overclaiming.** A pilot with 7 tasks and 1 run does not support
      "FormicOS demonstrates X." It supports "in this pilot, we observed Y."
- [ ] **Failures documented.** Failed tasks are analyzed, not hidden.
