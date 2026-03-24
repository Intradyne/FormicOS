# Wave 47 Acceptance Gates

Wave 47 is accepted when the coding-fluency improvements are truthful,
replay-safe, and clearly product-first.

## Gate 1: Surgical Editing Is Real

Must be true:

- a first-class `patch_file` tool exists in the engine tool surface
- the Coder can use it through normal caste/tool configuration
- zero matches return a useful self-correction error with context
- multiple matches return a useful ambiguity error with locations
- multi-operation calls apply sequentially against an in-memory buffer
- file writes are atomic: partial failure leaves the file unchanged

Fail if:

- the tool silently rewrites whole files on mismatch
- the failure contract is vague or untestable
- the tool only exists in docs/tests and not in runtime dispatch

## Gate 2: Fast Path Is Replay Truth

Must be true:

- the Queen can request `fast_path` at spawn time
- the choice is preserved through spawn/event/projection/replay truth
- older event logs replay with `fast_path=False`
- fast path is bounded to the intended single-agent/simple-task use
- fast-path colonies still emit normal event truth and still extract knowledge

Fail if:

- `fast_path` exists only as local runner state
- replay loses the execution mode choice
- the implementation turns into a second execution engine

## Gate 3: Structural Context Stays Current

Must be true:

- colonies with `target_files` refresh structural context per round
- the refreshed structure is visible in the Coder round context
- changes made through `workspace_execute` are not missed just because they
  bypass file-write tools
- non-coding colonies do not pay unnecessary refresh cost

Fail if:

- structure is still computed only once at colony start
- refresh only happens for explicit write tools
- the context exists in metadata only and never reaches the prompt

## Gate 4: Git Workflow Primitives Exist

Must be true for the accepted subset:

- `git_status`
- `git_diff`
- `git_commit`
- `git_log`

These should be first-class tool handlers with useful structured or bounded
output, not recipe-level shell snippets pretending to be tools.

Fail if:

- git support is still just "use workspace_execute manually"
- the tools are unsafe or include remote/destructive operations

## Gate 5: Product Identity Holds

Must be true:

- no benchmark-specific runtime path was added
- no task-specific heuristics were added to game coding suites
- each Must item clearly helps arbitrary operator coding tasks

Fail if:

- any shipped behavior exists primarily to score well on a benchmark
- the product runtime special-cases evaluation tasks

## Gate 6: Preview Is Truthful

Should be true:

- `preview=true` works on both `spawn_colony` and `spawn_parallel`
- preview returns plan/estimate truth without dispatching work
- fast-path previews surface the simplified mode honestly

Fail if:

- preview only works on the less important spawn path
- preview claims execution details it cannot really know

## Gate 7: Progress Summary Stays Bounded

Should be true:

- any Wave 47 progress summary is frontend-derived from existing truth
- no casual event-model growth was introduced just for a nicer status string
- if the summary proved awkward, it was deferred honestly to Wave 48

Fail if:

- event contracts were expanded without strong justification
- the UI shows fabricated progress details

## Gate 8: Docs and Recipes Match Reality

Should be true:

- caste recipes mention the new tools and fast-path behavior accurately
- operator-facing docs explain preview/fast-path behavior truthfully
- Wave 47 docs reflect what shipped and what deferred

Fail if:

- prompts tell agents to use tools that do not actually exist
- docs overclaim preview/progress support or replay behavior
