# ADR-007: Agent Tool System via LLM Tool Specs

**Status:** Proposed
**Date:** 2026-03-13

## Context

Caste recipes define tools per agent role (e.g. `memory_search`, `memory_write`,
`web_search`). Currently agents receive system prompts referencing these tools
but `runner.py` calls `llm_port.complete()` with `tools=None`. Agents cannot
actually invoke any tool. This makes the Researcher, Reviewer, and Archivist
castes non-functional beyond raw text completion.

Both LLM adapters (`llm_openai_compatible.py` and `llm_anthropic.py`) already
accept `tools: Sequence[LLMToolSpec]` and return `tool_calls` in `LLMResponse`.
The infrastructure exists — it just is not wired.

## Decision

Agent tools are implemented as **LLM tool specs passed to `llm_port.complete()`
with a tool-call-then-result loop in the runner**. The runner interprets tool
calls, executes them against real adapters (VectorPort, etc.), and feeds results
back as `tool` role messages in a second LLM call.

Specifically:

1. The runner builds `LLMToolSpec` dicts from the agent's `recipe.tools` list.
2. Each tool name maps to a handler function that calls the appropriate adapter.
3. When `llm_port.complete()` returns `tool_calls`, the runner executes each
   tool call, appends the results as `{"role": "tool", ...}` messages, and
   calls `llm_port.complete()` again with the extended message list.
4. Maximum 3 tool iterations per agent turn (prevents infinite tool loops).
5. Unknown tool names are returned as error messages to the LLM, not raised.

**Why not a separate tool execution framework?**

A standalone tool executor (like LangChain's `AgentExecutor` or a custom
middleware) would add a new abstraction layer, new error handling paths, and
new testing surface for no gain. The LLM adapters already handle tool calling
natively. The runner already has the agent turn lifecycle. Inserting tool
execution into the existing `_run_agent` method is ~60 lines, not a new module.

**Why not MCP tools for agents?**

MCP tools (ADR-005) are the *external* programmatic API — for the Queen, for
external agents, for the operator. Colony worker agents operate *inside* the
round loop where latency matters and the adapters are already injected. Adding
an MCP round-trip per tool call would add ~50ms overhead per call and require
serializing adapter state across a protocol boundary. Worker agent tools call
adapters directly.

## Alpha Tool Inventory

| Tool Name | Handler | Adapter | Available To |
|-----------|---------|---------|--------------|
| `memory_search` | `vector_port.search(collection, query, top_k=5)` | VectorPort | reviewer, researcher, archivist |
| `memory_write` | `vector_port.upsert(collection, docs)` | VectorPort | researcher, archivist |
| `query_events` | `event_store.query(address, event_type, limit=20)` | EventStorePort | queen (via MCP only) |

Future tools (`code_execute`, `file_read`, `file_write`, `web_search`) are
deferred to post-alpha and gated behind the SandboxPort (already defined in
`ports.py`, no adapter yet). Their tool specs should NOT be built until the
sandbox adapter exists — passing tool specs for non-functional tools causes
the LLM to attempt calls that return errors, degrading output quality.

**Critical:** `caste_recipes.yaml` must be updated to list ONLY the tools
that have working handlers. Remove `code_execute`, `file_read`, `file_write`,
`web_search` from caste tool lists until their handlers exist.

## Tool Call Loop Guardrails

- **Max iterations:** 3 tool-call rounds per agent turn. After 3, the runner
  appends a system message "Tool call limit reached, provide your final answer"
  and makes one last completion call with `tools=None`.
- **Per-tool output cap:** Tool results are truncated to 2000 characters before
  injection into the message list. This prevents a single vector search from
  consuming the entire context budget.
- **Error isolation:** Failed tool calls return a structured error message to
  the LLM (`"Tool memory_search failed: collection not found"`), never raise
  exceptions. The LLM can then decide to try a different approach.

## Consequences

- **Good:** Agents can actually use their declared tools. The Archivist can
  persist knowledge. The Researcher can query the skill bank. The feedback loop
  from colonies to the skill bank closes.
- **Good:** No new dependencies or abstraction layers. Uses existing adapters.
- **Bad:** Tool execution happens inside the agent turn, extending turn duration.
  A slow vector search adds latency to every agent that calls it.
- **Acceptable:** At alpha scale (2-5 agents, 1-2 tool calls each), the
  overhead is negligible compared to LLM inference time (seconds vs milliseconds).

## FormicOS Impact

Affects: `engine/runner.py`, `config/caste_recipes.yaml`.
Reads: `core/types.py` (LLMToolSpec), `core/ports.py` (VectorPort).
