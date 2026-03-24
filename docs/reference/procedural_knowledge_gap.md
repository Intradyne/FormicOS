# Procedural Knowledge Gap Analysis

What the model knows, what it doesn't, and where the missing layer should go.

> **STATUS (2026-03-23):** The primary recommendation — operational playbook at
> context position 2.5 — was **IMPLEMENTED in Wave 54** via `engine/playbook_loader.py`
> with task-class × caste resolution. Common mistakes at position 2.6 **IMPLEMENTED
> in Wave 56.5**. Convergence status injection **IMPLEMENTED in Wave 54** via
> `build_budget_block()` with stall_count/convergence_progress params. The reactive
> mid-turn correction (runner.py:1404) remains unimplemented. See
> `docs/specs/context_assembly.md` for the current-state spec.

---

## The two knowledge systems FormicOS needs

### Domain knowledge (exists, working)

The knowledge catalog is a fully operational Bayesian retrieval system:
- Thompson Sampling exploration with Beta(alpha, beta) posteriors
- 6-signal composite scoring (semantic, thompson, freshness, status, thread, cooccurrence)
- Tiered retrieval (summary → standard → full → auto)
- Decay classes (ephemeral γ=0.98, stable γ=0.995, permanent γ=1.0)
- Co-occurrence reinforcement, federated trust discounting
- Operator overlays (pin/unpin, mute/unmute, invalidate/reinstate)

This system answers: "What does the organization know about this domain?"

### Procedural knowledge (missing)

No system exists for: "How should an agent operate inside FormicOS?"

The model receives tool descriptions (what each tool does) but zero guidance on:
- **When** to use each tool relative to a task lifecycle
- **In what sequence** tools should be called for different task classes
- **What constitutes productive work** vs. spinning
- **How to recover** from a failed tool call or stall
- **What the colony lifecycle looks like** from the agent's perspective

---

## What the model currently receives vs. what it needs

### Currently injected (verified from source)

| Block | Content | Answers |
|-------|---------|---------|
| System prompt | "You are a Coder agent. Tools: memory_search, memory_write, code_execute, …" | "What am I? What can I do?" |
| Round goal | "Write a Python module that reads CSV…" | "What should I produce?" |
| Workspace structure | `[Workspace Structure] src/ tests/ ...` | "What files exist?" |
| System knowledge | `[SKILL, ACTIVE, INST] "Title": preview` | "What does the org know about this domain?" |
| Budget block | "Budget: $1.50/$5.00, Iteration 2/25, Round 3/10" | "How much time/money do I have left?" |
| Previous round | "Previous round: agent produced X…" | "What happened before?" |
| Routed outputs | "[coder_0]: I wrote the implementation…" | "What did other agents do this round?" |

### Not injected (the gap)

| Missing block | Would answer | Impact on behavior |
|---------------|-------------|-------------------|
| Task-class workflow | "For a code-writing task: (1) read existing files, (2) write implementation, (3) execute tests, (4) iterate on failures" | Model would know the expected work sequence |
| Few-shot tool examples | "To write a file, call write_workspace_file with path='src/mod.py' and content='…'" | Model would see correct tool-call JSON format |
| Convergence status | "Colony status: STALLING (3 consecutive rounds with no progress)" | Model would know to try something different |
| Tool-use feedback | "Last turn: you called list_workspace_files 4 times. Try write_workspace_file next." | Model would see what it's repeating |
| Productive work definition | "Productive actions: write_workspace_file, patch_file, code_execute. Observation-only actions: list_workspace_files, read_workspace_file, git_status." | Model would know which tools advance the task |
| Stall recovery playbook | "If stalled: (1) re-read the goal, (2) write a minimal implementation, (3) test it. Do not re-list files." | Model would have a fallback strategy |

---

## Evidence from experiments

### Experiment 1: tool_choice=required, full palette (16 tools)

[toolchoice_experiment_results.md](docs/waves/wave_53/toolchoice_experiment_results.md)

Model produced valid structured tool calls (0 parse failures) but called:
- `scratch_memory search` → 109 times (knowledge escape hatch)
- `code_execute` → 5 times
- `write_workspace_file` → 0 times

**Diagnosis:** Model can produce JSON. Model cannot select the right tool.

### Experiment 2: tool_choice=required, reduced palette (6 tools)

[reduced_tools_results.md](docs/waves/wave_53/reduced_tools_results.md)

With only productive tools available, model called:
- `workspace_execute ls -R` → 36 times
- `workspace_execute mkdir` → 44 times
- `write_workspace_file` → 0 times
- `code_execute` → 0 times

**Diagnosis:** Without knowledge escape hatches, model hides in `ls`/`mkdir` loops. It creates project structure but never writes code. This is not choice overload — it's missing procedural understanding of what "do the task" means in tool-call terms.

### Experiment 3: Qwen2.5-Coder-7B, no tool_choice

[qwen25coder_smoke_results.md](docs/waves/wave_53/qwen25coder_smoke_results.md)

Code-specialized model on csv-analyzer:
- `code_execute` → 14 times
- Quality: 0.2553 (within baseline range despite 14x more tool calls)

**Diagnosis:** A model that understands code can select productive tools. But 14 code executions didn't improve quality — the model writes code but not *correct* code for the task. The procedural understanding ("write code → test → fix failures → iterate") exists in the code-specialized model but not in the general model.

---

## The three capability layers

The experiment chain isolates three independent capabilities:

```
Layer 3: Code generation quality     ← requires model intelligence (7B+ code-specialized)
Layer 2: Tool selection              ← requires procedural knowledge (what to call when)
Layer 1: Structured output           ← requires tool_choice or model training
```

| Layer | Qwen3-30B-A3B (3.3B active) | Qwen2.5-Coder-7B (7B dense) |
|-------|:--:|:--:|
| Structured output | Fails without tool_choice | Works (~86% success) |
| Tool selection | Fails (spams knowledge/ls) | Works for simple tasks, fails for complex |
| Code quality | N/A (can't call tools) | Moderate (correct structure, wrong logic) |

**Layer 2 is the addressable gap.** Layer 1 is an adapter/model problem. Layer 3 is a model scale problem. But Layer 2 — procedural knowledge about tool selection — is a context engineering problem that can be addressed without changing models or adapters.

---

## Where procedural knowledge should NOT go

### Not in the knowledge catalog

The knowledge catalog stores domain knowledge with Bayesian confidence.
Procedural knowledge about "how to be a FormicOS agent" is:
- Static (doesn't evolve with observations)
- Not domain-specific (applies to all tasks)
- Not confidence-weighted (it's either correct or not)
- Not subject to Thompson Sampling or decay

Putting "call write_workspace_file to write code" in the knowledge catalog would pollute the retrieval system with entries that score high on semantic similarity to every coding task but carry no domain insight.

### Not in the system prompt alone

The coder system prompt is already 30+ lines. Adding full workflow playbooks would push important instructions deep into middle context where attention drops. The system prompt should identify tools; procedural guidance should be a separate context block with its own attention position.

### Not as operator directives

Directives are per-colony runtime injections for exceptional situations. Procedural knowledge is baseline operational guidance that should always be present.

---

## Where procedural knowledge SHOULD go

### Recommended: New context tier between goal and knowledge

Insert as position 2.5 in the assembly order (after round goal, before system knowledge):

```
 pos  block
 ───  ─────────────────────
  0   System prompt (identity + tools list)
  1   Budget block
  2   Round goal
 *2.5 [Operational Guidance] ← NEW
  2a  [Workspace Structure]
  2c  [System Knowledge]
  3   Routed outputs
  5   Previous round
```

### Injection point

[context.py:385–387](src/formicos/engine/context.py#L385-L387) — after round goal, before structural context:

```python
# After line 385 (round goal):
if operational_guidance:
    guidance_text = _truncate(
        f"[Operational Guidance]\n{operational_guidance}",
        budgets.goal,  # ~500 tokens
    )
    messages.append({"role": "system", "content": guidance_text})
```

### Content structure

The guidance block should be task-class-aware and model-capability-aware:

```
[Operational Guidance]

Workflow for code-writing tasks:
1. Read existing workspace files to understand the project structure.
2. Write your implementation using write_workspace_file.
3. Execute tests using code_execute to verify correctness.
4. If tests fail, read the output, patch the code, and re-test.
5. Each round should produce at least one write_workspace_file or code_execute call.

Productive tools (advance the task):
  write_workspace_file, patch_file, code_execute, workspace_execute

Observation tools (gather information, do not advance):
  list_workspace_files, read_workspace_file, git_status, git_diff

Do not call observation tools more than twice in a row without calling a productive tool.
```

### Reactive variant (per-iteration)

In addition to the static block above, a reactive correction could be injected in the tool-call loop ([runner.py:1404](src/formicos/engine/runner.py#L1404)):

```python
# Count tool categories in this turn
productive_calls = sum(1 for t in all_tool_names if t in PRODUCTIVE_TOOLS)
observation_calls = sum(1 for t in all_tool_names if t in OBSERVATION_TOOLS)

if iteration > 2 and productive_calls == 0 and observation_calls > 3:
    injected_messages.insert(2, {
        "role": "system",
        "content": "[Mid-turn guidance] You have made only observation calls. "
                   "Call write_workspace_file or code_execute to advance the task."
    })
```

---

## Seam inventory for implementation

| Seam | File | Line | Change type | Difficulty |
|------|------|------|------------|------------|
| Add `operational_guidance` param to `assemble_context()` | context.py | 348 | Add optional param + conditional block | Low |
| Add `operational_guidance` to `ColonyContext` | runner_types.py | varies | Add field to Pydantic model | Low |
| Build guidance string from task class | colony_manager.py | 681–695 | Task classification + template | Medium |
| Thread guidance through `run_round()` → `_run_agent()` → `assemble_context()` | runner.py | 1044, 1313 | Pass-through | Low |
| Add reactive mid-turn correction | runner.py | 1404 | Per-iteration tool history check | Medium |
| Add convergence status to context | colony_manager.py → context.py | varies | Thread stall_count/convergence | Low |
| Task-class detection | New function | New | Classify task → select guidance template | Medium |

### Minimal viable experiment

The smallest change that tests the hypothesis:

1. Edit `assemble_context()` to accept `operational_guidance: str | None = None`
2. Insert as system message at position 2.5 if present
3. Hardcode a single guidance string in `colony_manager.py` for the smoke
4. Run csv-analyzer + markdown-parser with Qwen3-30B + tool_choice=required

If the model calls `write_workspace_file` even once, procedural guidance works.

---

## Relationship to existing FormicOS systems

| System | Purpose | Procedural knowledge relationship |
|--------|---------|----------------------------------|
| Knowledge catalog | Domain retrieval (Thompson Sampling) | Separate concern — domain vs. operational |
| Proactive intelligence | 14 deterministic briefing rules | Could emit procedural hints as rule outputs |
| Workflow steps | Queen scaffolding for multi-colony work | Steps guide the Queen; procedural knowledge guides agents within a colony |
| Operator directives | Runtime injection for exceptional situations | Directives are operator-initiated; procedural guidance is system-default |
| Execution discipline scaffold | 3 rules in system prompt | Current scaffold is necessary but insufficient — it says "keep working" but not "how to work" |

The procedural knowledge layer fills a gap between "what tools exist" (system prompt) and "what domain knowledge applies" (knowledge catalog). It's the operational playbook that tells agents how to be productive inside the FormicOS architecture.
