# Procedural Guidance Injection for Small-Model Agent Systems

> **STATUS (2026-03-23):** The primary recommendation from this research — playbook
> injection at context position 2.5 — was **IMPLEMENTED in Wave 54**. Common mistakes
> injection at position 2.6 was **IMPLEMENTED in Wave 56.5**. Convergence status in
> the budget block was **IMPLEMENTED in Wave 54**. Reactive mid-turn correction
> (Section 4) remains unimplemented. See `docs/specs/context_assembly.md` and
> `docs/specs/colony_execution.md` for current-state specs.

**The single highest-leverage fix for FormicOS's observation-tool spam is injecting a task-class-keyed procedural playbook at context.py:385-387 (position 2.5 in context assembly), containing a 150–250 token step-by-step recipe with one few-shot tool-call example.** This addresses a failure mode that six experiments confirmed is not a tool surface, formatting, or prompting problem but a missing procedural knowledge layer. Research across nine production agent systems, the SkillsBench benchmark, and LangChain's few-shot studies converges on one conclusion: small models (≤10B active parameters) cannot reliably infer operational sequences from tool descriptions alone but follow explicit step-by-step recipes with remarkable fidelity. A 3.3B-active MoE model like Qwen3-30B-A3B sits at exactly the threshold where externally provided procedural structure becomes effective, according to the "Big Reasoning with Small Models" study — and where self-generated reasoning chains still fail.

---

## 1. How nine production systems inject operational guidance

Every major coding agent system maintains a **separate procedural guidance layer** between the system prompt and task content. None relies solely on tool descriptions or system prompts to drive workflow behavior. The table below captures the key patterns:

| System | What | Where in context | When | Size | Format |
|---|---|---|---|---|---|
| **Claude Code** (CLAUDE.md) | Project overview, workflows, commands, conventions, file boundaries, gotchas | After system prompt, before user messages; becomes part of system prompt | Static per-session; auto-loaded | <200 lines recommended | Markdown with `@import` progressive disclosure |
| **Cursor Rules** | Coding standards, framework patterns, per-file-type guidance | System area in `<cursor_rules_context>` and `<available_instruction_rules>` | 4 types: always-on, file-glob-triggered, agent-requested, manual | 50–200 lines per rule file; 10–20+ files per project | `.mdc` (Markdown + YAML frontmatter with globs) |
| **Aider** | Library preferences, type hints, code style | Read-only context alongside editable files | Per-session via `.aider.conf.yml` | ~50–100 lines | Plain Markdown (CONVENTIONS.md) |
| **SWE-Agent** | Constrained ACI command set, demo trajectory, tips | System message (~800 words) → demo → task | Static commands/demos; reactive error feedback; automatic context compression | ~800-word system message | ReAct (thought + command); deterministic formatted feedback |
| **smolagents** | Python function signatures as tools; format instructions | SystemPromptStep + accumulated execution log | Static system prompt; per-step state accumulation | Compact; tools as function signatures | Python code blocks (code-as-action, not JSON) |
| **OpenHands** | Event-stream actions/observations; AgentSkills library; micro-agent specs | Chronological event log as agent state | Per-turn accumulated; skills at instantiation | Full event history with compression | Python code actions; structured event objects |
| **Goose** | MCP tool defs, error feedback, RPI plan with verification criteria | Tools at session start; errors as observations; plan as persistent doc | Per-session (tools), reactive (errors), per-task (plan) | Variable | JSON-RPC (MCP); verbatim terminal output as feedback |
| **Cline** | Plan mode output (read-only exploration + strategy); `.clinerules` | Plan output = conversation history carried into Act mode; system prompt switches per mode | User-controlled mode toggle; context persists across switch | Plans: hundreds–thousands of tokens | Natural language; optional Markdown plan files |
| **Devin** | Preliminary plan + relevant files; persistent knowledge base | Between task description and autonomous execution | Per-task (interactive planning); knowledge base persistent | Detailed multi-step plans | Natural language; interactive chat |

Three cross-cutting patterns emerge. **First**, every system separates workflow guidance from tool definitions. SWE-Agent's ~800-word system message includes a complete demonstration trajectory. Claude Code's CLAUDE.md carries explicit workflow recipes ("explore-plan-code-commit for features, TDD for algorithmic work"). Cursor's rule system has four injection tiers with file-glob-triggered precision. **Second**, constraint-as-guidance is highly effective: SWE-Agent's constrained ACI improved performance by **10.7 percentage points** over raw shell access, and its ablation study found that giving agents too many search tools actually *degraded* performance below having no search tools at all — from 15.7% to 12.0%. This directly parallels FormicOS's `memory_search` 109× pattern. **Third**, error feedback injected as observations (Goose, SWE-Agent) drives self-correction without requiring new event types — the tool response itself carries the corrective signal.

The smolagents code-as-action pattern deserves special attention. Instead of JSON tool calls, the model writes Python that calls tools as functions: `write_workspace_file("main.py", code)` rather than `{"name": "write_workspace_file", "arguments": {...}}`. This achieved **20% higher success rates** and **30% fewer steps** across 17 LLMs, with improvements "more prominent in open-source/smaller models." The model already writes correct Python as prose — code-as-action eliminates the translation gap entirely. However, adopting it requires architectural changes to FormicOS's tool dispatch, making it a Phase 2 optimization rather than the immediate fix.

---

## 2. Recommended playbook architecture for FormicOS

### Where playbooks live

Store playbooks as **static YAML files outside the knowledge system**, deterministically selected by caste + task class. Do not inject them through the Bayesian retrieval substrate. The SkillsBench benchmark (February 2026) tested 7,308 trajectories across 7 agent-model configurations and found that **curated skills raised pass rates by +16.2 percentage points** while self-generated skills provided **zero average benefit (−1.3pp)**. The knowledge retrieval system is optimized for domain facts with uncertain relevance; procedural knowledge requires high-precision matching on task class, not fuzzy semantic similarity. Mixing procedures into the general retrieval pool risks what ReMe calls "toxic noise" contaminating domain knowledge retrieval.

**File location**: `config/playbooks/` directory, one YAML file per task class. The playbook loader reads `caste_recipes.yaml` to determine which playbooks apply to each caste.

```yaml
# config/playbooks/code_implementation.yaml
task_class: code_implementation
castes: [coder]
playbook:
  steps: |
    1. Read the target file with read_workspace_file
    2. Write your implementation with write_workspace_file
    3. Run tests with workspace_execute
    4. If tests fail, patch with patch_file and re-run
  productive_tools: [write_workspace_file, patch_file, code_execute, workspace_execute]
  observation_tools: [list_workspace_files, read_workspace_file, memory_search]
  observation_limit: 2
  example:
    tool: write_workspace_file
    arguments:
      file_path: "src/main.py"
      content: "def solve(n):\n    return n * 2\n"
```

### How playbooks are selected

The existing task classifier output (code_implementation, code_review, research, design, creative) maps directly to playbook filenames. In `context.py`, the `task_class` field from colony_manager.py's goal assignment selects the matching playbook. Fallback: if no task class is available, use the caste's default playbook.

### Injection point and token budget

**Primary injection**: context.py:385-387 (position 2.5 — after round goal, before workspace structure). This position exploits primacy effects while keeping procedural guidance adjacent to the goal it operationalizes.

**Token budget**: **200–300 tokens** for the playbook block. Research strongly supports this range. The "Big Reasoning with Small Models" study found that **longer prompts systematically reduced performance by −8 percentage points per log-unit increase in tokens** for small models. The LangChain benchmark showed 3 examples are optimal with diminishing returns beyond that. With the existing system prompt at ~800 tokens and knowledge cap at ~800 tokens, adding 250 tokens of playbook keeps total guidance under 1,850 tokens — well within the safe budget for a 3.3B-active model.

**Secondary (reactive) injection**: runner.py:1404 (inside the per-iteration tool-call loop). Triggered when observation tool count exceeds threshold. Details in Section 4.

### Context block format

```xml
<operational_playbook task_class="code_implementation">
WORKFLOW: Read target → Write implementation → Test → Iterate
STEPS:
1. Read the target file once with read_workspace_file
2. Write your full implementation with write_workspace_file
3. Run tests with workspace_execute
4. If tests fail, fix with patch_file then re-run

REQUIRED TOOLS: write_workspace_file, patch_file, workspace_execute
LIMIT: Call list_workspace_files or memory_search at most 2 times total

EXAMPLE tool call:
{"name": "write_workspace_file", "arguments": {"file_path": "src/main.py", "content": "def solve(n):\n    return n * 2\n"}}
</operational_playbook>
```

The XML-tagged block format serves two purposes: it's parseable for programmatic extraction, and XML tags help small models distinguish structural sections. The few-shot example uses the exact Hermes JSON format that Qwen3-30B-A3B was trained on.

---

## 3. Five concrete playbook cards

Each card is designed for **~200 tokens**, uses only positive directives (research confirms negative instructions hurt small models — they perform worse or ignore "do NOT" patterns), includes the productive/observation tool classification, and provides one few-shot example in the exact tool schema format.

### Card 1: code_implementation

```
WORKFLOW: Read → Write → Test → Iterate
STEPS:
1. Read the target file with read_workspace_file (once)
2. Write your complete implementation with write_workspace_file
3. Verify with workspace_execute or code_execute
4. Fix failures with patch_file, then re-test

PRODUCTIVE TOOLS: write_workspace_file, patch_file, code_execute, workspace_execute
OBSERVATION TOOLS (limit 2 total): list_workspace_files, read_workspace_file, memory_search

EXAMPLE:
{"name": "write_workspace_file", "arguments": {"file_path": "src/solver.py", "content": "import sys\n\ndef solve(data):\n    result = []\n    for item in data:\n        result.append(item * 2)\n    return result\n"}}
```

### Card 2: code_review

```
WORKFLOW: Read → Analyze → Write feedback → Suggest patches
STEPS:
1. Read the file under review with read_workspace_file
2. Check recent changes with git_diff
3. Write your review with write_workspace_file to a review file
4. Suggest fixes with patch_file on the target

PRODUCTIVE TOOLS: write_workspace_file, patch_file, git_diff, git_status
OBSERVATION TOOLS (limit 3 total): read_workspace_file, list_workspace_files, memory_search

EXAMPLE:
{"name": "patch_file", "arguments": {"file_path": "src/handler.py", "patches": [{"find": "except Exception:", "replace": "except ValueError as e:\n    logger.error(f'Validation failed: {e}')"}]}}
```

### Card 3: research

```
WORKFLOW: Search → Synthesize → Write findings
STEPS:
1. Search existing knowledge with memory_search (up to 3 times)
2. Read relevant workspace files with read_workspace_file
3. Write your findings document with write_workspace_file
4. Commit with git_commit when findings are complete

PRODUCTIVE TOOLS: write_workspace_file, git_commit
OBSERVATION TOOLS (limit 4 total): memory_search, read_workspace_file, list_workspace_files

EXAMPLE:
{"name": "write_workspace_file", "arguments": {"file_path": "docs/findings.md", "content": "# Research Findings\n\n## Summary\nThe analysis shows three key patterns...\n"}}
```

### Card 4: design

```
WORKFLOW: Survey → Design → Document → Validate
STEPS:
1. Survey existing structure with list_workspace_files (once)
2. Read key files with read_workspace_file (up to 3)
3. Write your design document with write_workspace_file
4. Create skeleton files with write_workspace_file for each component

PRODUCTIVE TOOLS: write_workspace_file, patch_file
OBSERVATION TOOLS (limit 4 total): list_workspace_files, read_workspace_file, memory_search, git_status

EXAMPLE:
{"name": "write_workspace_file", "arguments": {"file_path": "docs/design.md", "content": "# Component Design\n\n## Architecture\n- Module A handles input parsing\n- Module B handles transformation\n"}}
```

### Card 5: creative

```
WORKFLOW: Explore → Draft → Refine → Deliver
STEPS:
1. Review any reference material with read_workspace_file
2. Write your first draft with write_workspace_file
3. Refine by patching with patch_file
4. Finalize and commit with git_commit

PRODUCTIVE TOOLS: write_workspace_file, patch_file, git_commit
OBSERVATION TOOLS (limit 2 total): read_workspace_file, memory_search

EXAMPLE:
{"name": "write_workspace_file", "arguments": {"file_path": "output/draft.md", "content": "# Title\n\nOpening paragraph that establishes the core theme...\n"}}
```

---

## 4. Reactive mid-turn correction at runner.py:1404

The per-iteration tool-call loop at runner.py:1404 already processes each tool call sequentially. The reactive correction injects a synthetic assistant/user message pair when the model enters an observation loop.

### Trigger conditions

Track two counters within the current turn's tool-call sequence:

- **observation_count**: incremented when the tool name is in `{list_workspace_files, read_workspace_file, memory_search, git_status, git_diff}`
- **productive_count**: incremented when the tool name is in `{write_workspace_file, patch_file, code_execute, workspace_execute, git_commit}`

Fire the correction when **observation_count ≥ 3 AND productive_count == 0** within the current turn.

### Injection content

Inject as the tool response to the most recent observation call (this exploits recency bias — research confirms small models attend most strongly to the last few messages):

```
OBSERVATION LIMIT REACHED. You have called observation tools {observation_count} times without producing output.

YOUR NEXT CALL MUST BE: write_workspace_file or patch_file

Use the information you already have. Write your solution now.
```

**Token cost**: ~50 tokens. This fits within a tool response and requires no new event types — it rides the existing tool-response mechanism.

### Implementation sketch for runner.py:1404

```python
# Inside the per-iteration tool-call loop
obs_count = sum(1 for tc in turn_tool_calls if tc.name in OBSERVATION_TOOLS)
prod_count = sum(1 for tc in turn_tool_calls if tc.name in PRODUCTIVE_TOOLS)

if obs_count >= 3 and prod_count == 0:
    correction = (
        f"OBSERVATION LIMIT REACHED. You have called observation tools "
        f"{obs_count} times without producing output.\n\n"
        f"YOUR NEXT CALL MUST BE: write_workspace_file or patch_file\n\n"
        f"Use the information you already have. Write your solution now."
    )
    # Inject as the tool response content for the current call
    tool_response.content = correction + "\n\n" + tool_response.content
```

The correction uses **only positive directives**. Research across multiple benchmarks shows small models perform worse with negative instructions ("do NOT call ls again") than with positive redirects ("your next call must be write_workspace_file"). The LangChain few-shot study confirmed that corrective trajectories (where the model initially erred, then was redirected) are effective teaching signals.

### Escalation

If the model calls another observation tool after correction, inject `tool_choice={"type": "function", "function": {"name": "write_workspace_file"}}` for the next inference call. The user's experiments already showed `tool_choice=required` gives 0% parse failures — the model *can* produce the call when forced. This two-stage approach (soft correction → hard force) avoids the quality degradation of always-forced tool choice while breaking observation loops.

---

## 5. Convergence status injection into agent context

The system already computes stall detection (stability > 0.95 + progress < 0.01 + round > 2) and emits governance warnings as events, but these are **not visible to the agent**. Threading convergence status into context closes this feedback loop.

### Injection point

Append convergence status to the existing budget block in context assembly. The budget block already occupies a primacy-adjacent position and the agent is trained to attend to it. Adding 30–50 tokens to an existing block is cheaper than creating a new block.

### Format

```
PROGRESS: round {current_round}/{max_rounds} | stability={stability:.2f} | progress={progress:.2f}
STATUS: {status_label}
```

Where `status_label` is derived from the governance signals:

| Condition | Label |
|---|---|
| progress ≥ 0.3 | ON TRACK — continue current approach |
| 0.01 ≤ progress < 0.3 | SLOW — focus on productive tool calls |
| progress < 0.01 AND stability > 0.8 | STALLED — you must change approach. Write output now. |
| round ≥ max_rounds - 1 | FINAL ROUND — deliver your best output immediately |

**Token cost**: **30–50 tokens** appended to the budget block. The status labels are designed as behavioral nudges — "STALLED" with an imperative creates urgency, while "ON TRACK" confirms the current approach without consuming attention.

### Implementation

In context.py, wherever the budget block is assembled (likely near the round/budget metadata injection), append the convergence status. The `stall_count`, `stability`, and `progress` values already exist in colony_manager.py's governance state — they just need to be threaded through to context assembly.

---

## 6. Micro-trajectory extraction from existing transcripts

FormicOS's memory_extractor.py already harvests domain knowledge from transcripts. Extending it to extract procedural knowledge is feasible and well-supported by research.

### What the research says

**ExpeL** (AAAI 2024) extracts procedural insights from trajectories using two methods: success/failure comparison for the same task type, and cross-task pattern recognition across successful trajectories. Insights are managed with ADD/EDIT/UPVOTE/DOWNVOTE operators; importance counts below zero trigger removal. ExpeL achieved +36% on reasoning tasks through extracted insights.

**SkillRL** (February 2026) distills trajectories into a hierarchical SkillBank achieving **10–20× token compression** versus raw trajectory storage. General skills (cross-task strategies) and task-specific skills (category heuristics) co-evolve through recursive refinement.

**Critical caveat from SkillsBench**: Self-generated skills provide −1.3pp average benefit when generated *before* task execution. But skills distilled *after* successful execution — capturing what the agent learned through iteration — work well. The extraction must happen post-hoc from successful runs, not prospectively.

### Recommended extraction format

```yaml
skill_id: "proc_code_impl_001"
task_class: code_implementation
trigger: "When goal involves writing new code"
tool_sequence: [read_workspace_file, write_workspace_file, workspace_execute]
steps:
  - "Read target file to understand structure"
  - "Write complete implementation in one write_workspace_file call"
  - "Test with workspace_execute"
observation_tool_count: 1
productive_tool_count: 3
source_colony: "colony_2024_abc"
success_verified: true
importance_score: 2
```

### Quality filtering pipeline

The core challenge is distinguishing "procedure worked because good" from "procedure worked because task was easy." A four-stage filter addresses this:

1. **Outcome gate**: Only extract from colonies that achieved measurable success (goal completion, tests passing, deliverable produced)
2. **Efficiency gate**: Filter for trajectories where the ratio of productive-to-observation tool calls exceeds a threshold (e.g., productive/(productive + observation) > 0.3). This naturally excludes runs that succeeded despite inefficient tool use
3. **Cross-task validation**: An extracted skill must help on at least 2 different tasks before its importance score is promoted. ExpeL's UPVOTE/DOWNVOTE mechanism provides this
4. **Difficulty weighting**: Skills extracted from tasks the model initially struggled with (required >1 stall recovery) are more valuable than skills from tasks completed on the first try

### Extension to memory_extractor.py

Add a `ProcedureExtractor` class alongside the existing domain knowledge extractor. It receives the same transcript but looks for different patterns: tool-call sequences that led to successful outcomes, phase transitions (from observation to production), and recovery patterns (from stalling to progress). The output goes to `config/playbooks/learned/` as YAML files, separate from the curated playbooks, and requires human review before promotion to the active playbook set. This follows the "start curated (a), evolve toward learned (c)" trajectory that research strongly supports.

---

## 7. Evidence on few-shot examples versus verbal instructions

The evidence is unambiguous for small models: **few-shot tool-call examples dramatically outperform verbal instructions**.

**LangChain's benchmark** (July 2024) provides the strongest direct evidence. Claude 3 Haiku (a small model) achieved **11% correctness with zero-shot tool calling but 75% with just 3 trajectory examples as messages** — matching or exceeding the zero-shot performance of much larger models like Claude 3.5 Sonnet and GPT-4o. Larger models showed minimal improvement from few-shot, confirming that **smaller models benefit proportionally more**. Three examples matched performance of all nine examples, establishing 3 as the sweet spot with diminishing returns beyond.

**Format matters enormously**: LangChain found that few-shot examples formatted as **conversation messages** (separate user/assistant/tool turns) dramatically outperformed examples formatted as strings appended to the system prompt. Claude 3 models "improve little or not at all when examples are formatted as strings." For FormicOS, this means the few-shot example in the playbook should be formatted as a tool-call JSON in exactly the Hermes format Qwen3 was trained on, not as prose.

The "Big Reasoning with Small Models" study (arXiv 2510.13935) confirmed that models below ~3B parameters cannot follow retrieved instructions, but **once models cross the 3B threshold, externally provided step-by-step procedures shift from noise to usable structure**. Qwen3-30B-A3B's 3.3B active parameters sit at exactly this transition point. Longer prompts systematically reduced performance (−8pp per log-unit increase), reinforcing that **concise recipes plus one concrete example beats verbose instructions**.

**Negative examples hurt small models**. Research across multiple benchmarks shows LLMs are "really bad at following negative instructions" — negation understanding does not reliably improve with scale, and switching from negative to positive prompts "dramatically improved outcomes." Every playbook should use positive directives ("After reading the file, write your implementation with write_workspace_file") rather than prohibitions ("Do NOT call ls repeatedly").

**Task-class-keyed guidance outperforms generic guidance by a wide margin**. The ASDA framework achieved +17.33pp improvement by injecting task-specific skill files at inference time. SkillRL's hierarchical SkillBank with task-specific skills outperformed flat memory by 15.3%. The CLASSic benchmark showed domain-specific agents at 82.7% accuracy versus significantly lower for general-purpose approaches. FormicOS's existing task classifier (code_implementation, code_review, research, design, creative) maps directly to this pattern.

---

## 8. The single highest-leverage change

**Inject a task-class-keyed procedural playbook at context.py:385-387 containing a step-by-step recipe, tool classification, and one few-shot tool-call example.**

### Exact injection point

**File**: `context.py`, lines 385–387 (position 2.5 in context assembly, after round goal, before workspace structure)

### Content template

```xml
<operational_playbook>
WORKFLOW: {workflow_summary}
STEPS:
{numbered_steps}

PRODUCE OUTPUT WITH: {productive_tool_list}
GATHER INFO WITH (limit {n}): {observation_tool_list}

EXAMPLE:
{one_json_tool_call_in_hermes_format}
</operational_playbook>
```

Selected from `config/playbooks/{task_class}.yaml` based on the task classifier output in colony_manager.py. Total token cost: **200–250 tokens**.

### Why this is highest-leverage

This single change addresses all three dimensions of the failure mode simultaneously. It provides the **procedural sequence** the model lacks (read → write → test → iterate), which six experiments proved is the missing layer. It provides a **concrete tool-call example** in the exact format the model must produce, which LangChain's research showed increases small-model tool-calling accuracy from 11% to 75%. And it **classifies tools as productive versus observation** with an explicit call limit, which SWE-Agent's ablation proved is more effective than unrestricted tool access.

The position at 2.5 in context assembly exploits the primacy effect documented by Liu et al. (2023) and confirmed architecturally by the "Lost in the Middle at Birth" study — early context positions receive exponentially more attention through causal masking. It sits after the round goal (so the model knows *what* to do) but before workspace structure and knowledge (so the model knows *how* to do it before seeing the details it must act on).

### Expected behavioral change

Based on the LangChain few-shot results (11% → 75% for small models with 3 examples), SkillsBench findings (+16.2pp from curated skills), and SWE-Agent's action space constraint results (+10.7pp from constrained tools), the expected change is a shift from near-zero productive tool calls to a majority of tool calls being productive. The observation tool cap creates a forcing function: once the model has used its 2 allowed `list_workspace_files` calls, the playbook's step sequence and example direct it toward `write_workspace_file`. The reactive correction at runner.py:1404 provides a safety net if the model still loops, escalating from soft redirect to hard `tool_choice` forcing.

### Implementation priority

The recommended implementation sequence, ordered by leverage and implementation cost:

1. **Playbook injection at context.py:385-387** — highest leverage, ~2 hours to implement. Add the playbook loader, wire task_class selection, inject the XML block
2. **Convergence status in budget block** — 30 minutes. Thread existing stall_count/stability/progress values into context assembly
3. **Reactive correction at runner.py:1404** — 1 hour. Add observation/productive counters, inject correction as tool response, add tool_choice escalation
4. **Tool surface reduction** — medium effort. Reduce Coder caste from 16 tools to 5–6 based on task class. Qwen3 documentation confirms the model degrades with >5 tools, and SWE-Agent's ablation proves fewer well-designed tools outperform many tools
5. **Micro-trajectory extraction** — Phase 2. Extend memory_extractor.py with ProcedureExtractor after the curated playbooks prove effective

The first three changes are additive, require no architectural modifications, introduce no new event types or backend subsystems, and stay within the existing context assembly and runner loop seams. They work with 3.3B active parameters because they provide the external procedural structure that research consistently shows small models need but cannot generate for themselves.
