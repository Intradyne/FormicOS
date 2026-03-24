# Research Prompt: How Simple Agent Codebases Get Effective Tool Use From Small Local Models

## Context you must anchor on

This research is for FormicOS, a multi-agent colony framework that just completed
a diagnostic measurement arc. The findings are specific and load-bearing -- do not
generalize past them.

### The three-layer bottleneck (proven experimentally)

FormicOS runs Qwen3-30B-A3B (30B total, 3.3B active MoE) locally via llama.cpp.
Three experiments isolated three stacked failure layers:

1. **Structured output**: ~85% parse failure rate on moderate coding tasks.
   `tool_choice=required` eliminates this completely (0% parse failures).
   SOLVED at the API level.

2. **Tool selection**: With `tool_choice=required` and 12+ tools available,
   the model spams "safe" tools (knowledge_search, memory_write -- 109 events
   in one smoke test) instead of productive tools (code_execute, write_file).
   Quality DROPPED despite perfect JSON formatting. UNSOLVED.

3. **Code generation quality**: Even with correct tool selection, the 3.3B-active
   model produces mediocre code on moderate tasks (~0.25 quality score).
   UNSOLVED but separate from the tool-use problem.

### What we already know from our own research

From our project knowledge base:

- **mini-SWE-agent** (~100 lines) scores >74% on SWE-bench Verified with a SINGLE
  tool: bash. No tool-calling API. LLM writes bash as free text. "Tools are
  unnecessary if your single tool is a shell."

- **Simon Willison's llm tool-calling**: A full coding agent using just `read_file`,
  `list_files`, and `apply_diff` -- 3 tools total.

- **Anthropic computer-use demo** (~200 lines): 3 tools total: `computer`, `bash`,
  `str_replace_based_edit_tool`.

- **smolagents CodeAgent**: LLM writes Python code directly, tools are just
  callable functions in the generated code. No JSON tool-calling at all.

- **Our own experiment**: Qwen2.5-Coder-7B with `tool_choice=required` produced
  perfect structured tool calls on csv-analyzer (95% success, 14 code executions)
  but 100% failure on markdown-parser (wrote solution as prose). Task-dependent.

- **BFCL benchmark data**: Accuracy degrades above 10 tools. Manus uses logit
  masking rather than dynamic tool removal (preserves KV cache).

- **Grammar-constrained decoding**: Forces valid JSON but can DEGRADE reasoning
  by 27.3pp on GSM8K (Tam et al., EMNLP 2024). Reversed for weak models:
  Qwen2.5-Coder-7B went from 0% to 75% accuracy with grammar constraints.

### FormicOS's current coder tool set (the problem)

The Coder caste currently sees 16 tools:
`memory_search`, `memory_write`, `code_execute`, `workspace_execute`,
`list_workspace_files`, `read_workspace_file`, `write_workspace_file`,
`patch_file`, `git_status`, `git_diff`, `git_commit`, `git_log`,
`knowledge_detail`, `transcript_search`, `artifact_inspect`, `knowledge_feedback`

When forced to choose (`tool_choice=required`), the model retreats to
knowledge/memory tools instead of write/execute tools. The tool surface is
too large and the "safe" options are too attractive.

## What I need you to research

I want a focused investigation of how the simplest effective agent codebases --
particularly in the OpenClaw / Goose / Cline / Aider / mini-SWE-agent / Claude Code
lineage, plus any newer minimal frameworks (OpenFang, NanoClaw, NullClaw, or whatever
the current landscape calls them) -- achieve reliable tool use on local models.

### Specific questions (answer all of these)

**Q1: Tool surface design**

How many tools do the effective simple agents expose? What are they specifically?
I want exact tool names and descriptions from at least 5 codebases. I suspect
the answer is 3-5 tools, but I want the actual data.

For each codebase, answer:
- How many tools does the agent see at any given time?
- Are tools static or do they change per phase/turn?
- Is there a "god tool" pattern (e.g., bash/shell as the only tool)?
- How do they handle the "model retreats to safe tools" problem?
- Do they use `tool_choice` or equivalent forcing?

**Q2: The "bash as single tool" pattern**

mini-SWE-agent uses only bash. Others use shell + file edit + file read.
For a system like FormicOS that NEEDS workspace file operations, knowledge
retrieval, and code execution:

- What is the minimal tool set that covers these capabilities?
- Can knowledge retrieval be embedded in the system prompt context instead
  of being a callable tool? (i.e., inject relevant knowledge before the
  turn instead of letting the model choose to search)
- Is there evidence that removing the CHOICE to search knowledge and instead
  ALWAYS injecting it produces better outcomes?

**Q3: How do simple agents handle the "tool selection" problem specifically?**

FormicOS's layer-2 problem is that with 12+ tools, the model picks wrong.
How do effective simple codebases avoid this?

Investigate:
- Phase-aware tool filtering (different tools available at different stages)
- Progressive tool disclosure (start with 3, add more only if the model asks)
- Tool grouping / namespacing (does grouping help small models?)
- The Manus approach (logit masking to restrict without removing from context)
- Whether anyone successfully uses `tool_choice` with >5 tools on small models

**Q4: What specific prompting patterns do simple agents use for tool discipline?**

I already tried a three-instruction scaffold (persistence, tool discipline,
planning). It had negligible effect on Qwen3-30B-A3B. What works better?

Investigate:
- Few-shot tool-call examples in system prompts (how many? what format?)
- "Think step by step THEN call a tool" patterns vs interleaved thinking
- Explicit "do not call X tool unless Y condition" negative instructions
- The NLT (Natural Language Tools) approach where the model describes
  actions in natural language and a parser converts to tool calls
- Whether structured output schemas (not just tool_choice but full
  response_format) help with tool selection, not just formatting

**Q5: What do Aider, Cline, and Claude Code do differently that FormicOS doesn't?**

These are the most successful local-model coding agents. They work well with
models in the 7B-30B range. What specific patterns do they use?

For each, I want:
- Exact tool/command surface
- How they handle multi-file editing
- How they handle "the model wrote prose instead of a tool call"
- Whether they use structured output / tool_choice / grammar constraints
- How they recover from failed tool calls
- Whether they do ANY multi-agent coordination or are purely single-agent

**Q6: The "code as action" alternative**

smolagents' CodeAgent has the LLM write Python code directly instead of
JSON tool calls. Tools are just functions callable in the generated code.
This eliminates the tool-call formatting problem entirely.

- Who else uses this pattern in production?
- What are the failure modes? (I assume: code injection, hallucinated imports)
- Is there a hybrid where the model writes code for execution but uses
  structured tool calls for file I/O?
- Would this work with Qwen3-30B-A3B's capabilities?

**Q7: What is the current state of the art for local model tool calling
specifically on Qwen3 and Qwen2.5 models?**

Our model is Qwen3-30B-A3B via llama.cpp. We also have Qwen2.5-Coder-7B on disk.

- What chat templates produce the best tool-call reliability?
- Does the Unsloth-fixed template matter for Qwen3 specifically?
- What `tool_choice` / `parallel_tool_calls` / `strict` parameters does
  llama.cpp actually honor?
- Are there llama.cpp-specific flags (--grammar, --json-schema, etc.) that
  improve tool-call reliability without degrading reasoning?
- What temperature/top_p/top_k settings do successful Qwen3 tool-calling
  deployments use?

## What I do NOT want

- Do not recommend "switch to a cloud model" as the primary answer
- Do not recommend "add more tools" or "build a planning layer"
- Do not recommend MCP protocol changes (MCP is the external surface,
  not the internal tool plane)
- Do not describe tools or capabilities that do not exist in shipped code
  of the codebases you reference
- Do not conflate "works with GPT-4" with "works with 7B-30B local models"
- Do not give generic prompting advice -- ground everything in specific
  codebase evidence

## Deliverable shape

1. **Tool surface comparison table**: 5-8 codebases, exact tools, count,
   whether static or dynamic, any forcing mechanism

2. **The minimal viable tool set for a coding agent**: your evidence-based
   recommendation for what FormicOS's Coder should see, with justification

3. **Top 3 patterns that address tool selection on small models**: ranked
   by evidence strength, with specific implementation guidance

4. **Qwen3/Qwen2.5 specific findings**: exact template, parameters, and
   llama.cpp flags that maximize tool-call reliability

5. **One concrete recommendation**: if you had to make ONE change to
   FormicOS's Coder tool surface to most improve moderate-task quality,
   what would it be and why?

## Grounding constraint

Every recommendation must pass this test:

**If the benchmark disappeared tomorrow, would we still want this change?**

If the answer is "only to improve benchmark scores," skip it.
If the answer is "yes, because it makes the agent more reliable for real work," include it.
