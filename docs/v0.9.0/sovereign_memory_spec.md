# FormicOS v0.9.0 — Sovereign Memory Specification

**Goal**: Transform FormicOS from a text-based chatbot into a memory-safe Reasoning Engine via Recursive Language Models (arXiv:2512.24601).

FormicOS v0.9.0 introduces the **Sovereign Memory** layer, a memory architecture designed to allow Root_Architect agents to traverse massive 10M+ token codebases without Out-Of-Memory (OOM) crashes, while also providing secure, local project knowledge directly to external IDEs (like Cursor and Claude Desktop).

---

## 1. The mmap Sandbox & Topo-Memory

When dealing with massive repositories, it is impossible to inject the entire file into the LLM context window. FormicOS handles this via a Python REPL sandbox that interacts directly with a memory-mapped wrapper.

### 1.1 `SecuredTopologicalMemory` (50,000-byte Clamping)
The `SecuredTopologicalMemory` (in `src/core/repl/secured_memory.py`) wraps the `mmap` syscall. 
- It forces the LLM to access files via strict byte-ranges.
- Every `read_slice()` call is clamped to a `max_slice_bytes` limit (default **50,000 bytes**).
- If the LLM requests a larger window, it throws a `FormicMemoryError` with an instructive message, forcing the LLM to self-correct and narrow its search (e.g., via tighter regex or binary searching byte offsets). This prevents a single careless read from crashing the Docker container via an OOM error.

### 1.2 The AST Pre-Parser Guardrail
The REPL environment (`src/core/repl/harness.py`) executes code submitted by the agent using `exec()`. To prevent agents from hanging the executor thread or escaping the sandbox, code is passed through an `ASTValidator` before execution.
- **Banned Iteration**: `while` loops are totally banned. LLMs must use bounded `for` loops. This guarantees that code will eventually terminate.
- **Banned Escapes**: `time.sleep`, `os.system`, and `subprocess.*` calls are explicitly forbidden to prevent the agent from gaining unauthorized system access or permanently blocking the orchestrator.

## 2. The DyTopo Router & Subcalls

Complex tasks often require recursive decomposition. FormicOS allows the REPL sandbox to farm out specific sub-tasks to fresh sub-agents via the `formic_subcall` primitive.

### 2.1 Subcall Isolation (`route_subcall`)
When an agent calls `formic_subcall(task, data)` in the REPL:
1. The `formic_subcall` function blocks the REPL worker thread.
2. It calls `asyncio.run_coroutine_threadsafe(router.route_subcall(...))` to schedule the task on the main Python event loop.
3. The `SubcallRouter` (in `src/core/orchestrator/router.py`) creates a **perfectly isolated** fresh agent context. 
4. The sub-agent receives the exact `task` and `data` strings provided, but **does not inherit the Root_Architect's context tree or history**, starting perfectly clean. 
5. The string output of the sub-agent is returned directly back into the execution environment.

This isolation creates a clean functional abstraction for recursive sub-agents without blowing up the context window.

## 3. The Inbound MCP Server

FormicOS Sovereign Memory isn't just for internal agents. FormicOS runs an inbound Model Context Protocol (MCP) server over `stdio` (`src/mcp/inbound_memory_server.py`) to expose its persistent episodic and semantic memory to external clients like Cursor or Claude Desktop.

### 3.1 The `formic://` URI Scheme
By connecting your IDE to FormicOS's inward MCP port, the IDE gains native access to the memory graph:
- `formic://stigmergy/{colony_id}/state`: Read the full topological graph history, rounds, and metrics from the `.formicos/sessions/` context files.
- `formic://qdrant/{collection}/latest`: Access raw Qdrant vectors and payload content directly for custom semantic lookups.

### 3.2 Tools for the IDE
The MCP server exposes powerful tools directly to the IDE:
- `query_formic_memory`: Semantically search the `swarm_memory` Qdrant collection using BAAI/bge-m3 embeddings.
- `get_colony_failure_history`: Extract historical failure states (force halts, escalations, TKG errors) from prior sessions to aid in debugging.

### 3.3 The Superiority of Sovereign Memory
Modern IDEs often lock users into proprietary "Project Knowledge" vectors that live entirely on their cloud servers. **FormicOS Sovereign Memory** inverts this relationship. By exposing an MCP interface, the vectors, failure history, and topology graphs live locally on the user's filesystem (SQLite/Qdrant/JSON), preventing vendor lock-in. Any connected LLM—whether running locally via Ollama or remotely via Anthropic API—can be slotted into the IDE and query the exact same local sovereign knowledge graph.
