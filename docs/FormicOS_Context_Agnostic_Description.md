# FormicOS

**A local-first colony operating system for LLM agent swarms.**

---

## What it is

FormicOS orchestrates multiple LLM agents that collaborate on complex tasks by reading and writing to a shared environment rather than messaging each other directly. It runs entirely on local hardware by default, coordinating open-weights models through a hierarchical state structure called the Context Tree.

The system organizes work into **colonies** — isolated, pausable, resumable task units, each with its own agent pool, filesystem sandbox, vector store namespace, and execution state. A **supercolony** manages multiple concurrent colonies, tracks available model backends, and maintains a shared library of distilled skills that compounds across tasks.

FormicOS is not an LLM inference server, not a vector database, and not a chatbot. It orchestrates agents that use those tools.

---

## The core loop

Each colony runs an iterative refinement loop:

1. **Goal setting.** A privileged manager agent reviews the task and round history, then sets the current round's objective or terminates the colony.

2. **Intent declaration.** Each worker agent generates a short semantic descriptor: a *key* (what it offers) and a *query* (what it needs).

3. **Dynamic topology construction.** Descriptors are embedded via a lightweight sentence transformer. A cosine similarity matrix is computed, thresholded, capped by maximum in-degree, and converted to a directed acyclic graph via greedy cycle breaking and topological sort. This produces the communication graph for the round — who sends output to whom, in what order.

4. **DAG-ordered execution.** Agents execute in topological order. Each agent receives upstream outputs from its graph neighbors, its caste-specific system prompt, injected skills from the shared library, and assembled context from the tree. Each agent runs a bounded reactive planning loop of up to 10 LLM calls, using tools (file I/O, code execution, vector search, MCP-forwarded external tools) with human-in-the-loop approval gates on destructive operations.

5. **Compression and governance.** Agent outputs are summarized into a terse episode. Knowledge triples are extracted into a graph. Three independent monitors check for convergence (cosine similarity between consecutive round summaries), path diversity collapse (all agents using the same approach), and repeated failure patterns. The system takes the highest-severity action: continue, intervene with feedback, warn, or force-halt.

6. **Skill distillation (post-completion).** When a colony finishes, reusable heuristics are extracted from the trajectory, deduplicated against the existing library, and stored for future colonies.

The loop always terminates: it is bounded by a maximum round count, a convergence detector, manager-initiated termination, or external cancellation.

---

## What makes FormicOS different from flat agent frameworks

**Stigmergy, not message passing.** Agents coordinate by modifying shared artifacts — files in sandboxed workspaces, entries in the Context Tree — rather than sending direct messages. The communication topology is computed dynamically each round from semantic similarity between agent intents, not hardcoded.

**Hierarchical scoped memory, not a flat context window.** The "Context Rot" problem of standard LLMs is solved via Recursive Language Models (arXiv:2512.24601) and the Context Tree. Instead of loading massive files into a linear chat log, the `Root_Architect` operates inside a `SecuredTopologicalMemory` Python REPL, using `mmap` to map 100MB+ repositories directly to disk. The orchestrator reads bounded byte-slices, synthesizing insights without exceeding an 8k context window. These insights are then stored across six scopes with different staleness policies (supercolony state, system info, project structure, colony state, persistent knowledge, and RAG-backed semantic memory), ensuring agents receive a priority-ordered, budget-constrained assembly of relevant context.

**Colonies as sovereign economic units (The AaaS Transition).** While FormicOS runs locally, it is designed to participate in the broader Agent-to-Agent (A2A) economy. It features an optional `CFO` caste that manages a cryptographically secured Stigmergy ledger. Every outbound API call to external paid services (like AWS or PREA) is blocked by a Zero-Trust `EgressProxy`. The CFO must mathematically sign an `ExpenseRequest` using its Ed25519 Private Key before the proxy opens the socket, guaranteeing that FormicOS can operate autonomously in the cloud economy without runaway token spend or rogue egress.

**Topological Perception, not Euclidean Shredding.** Standard RAG pipelines use naive character splitters that destroy the structure of tables, lists, and code blocks. FormicOS utilizes the **Dockling Perception Layer**. The `AsyncDocumentIngestor` maps PDFs and complex documents topologically, generating semantically intact Markdown chunks. By running a local BGE-M3 embedding pass during ingestion, FormicOS ensures the Qdrant cluster is filled with geometrically whole concepts rather than arbitrarily fractured string sequences.

**Cross-colony learning through a shared skill library.** Skills distilled from completed colonies are available to all future colonies. Retrieval is by cosine similarity against the current round goal. Skills that correlate with successful outcomes are reinforced; skills that are never retrieved are pruned. The system gets better at each successive colony without any weight updates.

---

## Relationship to recent agent framework research

Two recent papers — **MiroFlow** (Su et al., Tsinghua / MiroMind AI, 2025) and **OmniGAIA** (Li et al., Renmin University / Xiaohongshu, Feb 2026) — validate, challenge, and extend several FormicOS design decisions.

### What MiroFlow validates

MiroFlow introduces an **agent graph** for flexible orchestration with hierarchical sub-agent delegation. Its core architecture — a main agent that decomposes tasks and coordinates specialized sub-agents, each with distinct tool access and context budgets — closely parallels FormicOS's manager/worker caste system with DyTopo routing. Both systems treat agent coordination as a graph problem where the structure changes based on task demands rather than being statically defined.

MiroFlow's demonstration that a complete research agent stack can run on a **single RTX 4090** with open-source models (MiroThinker) validates FormicOS's local-first constraint: the premise that 32 GB of VRAM and open-weights models are sufficient for substantive multi-agent work, without depending on cloud APIs as a baseline requirement.

MiroFlow's **interactive scaling** finding — that performance improves predictably as agent-environment interaction depth increases, establishing this as a third scaling dimension alongside model size and context length — directly validates FormicOS's multi-round iterative refinement loop. FormicOS was designed around the intuition that multiple passes through a task with compressed feedback between rounds would outperform a single-pass approach. MiroFlow provides empirical evidence: MiroThinker supports up to 600 tool calls per task across a 256K context window, and accuracy scales with interaction depth. This suggests FormicOS's default of 5–15 rounds with 5 agents may be conservative, and that the system should expose interaction budgets as a first-class tuning parameter.

### What MiroFlow challenges

MiroFlow's **recency-based context retention** strategy (the `keep_tool_result` parameter, which retains only the K most recent tool responses) is more pragmatic than FormicOS's hierarchical memory tier system. FormicOS uses episode compression, epoch summaries, and a temporal knowledge graph to manage context across rounds — elegant but complex. MiroFlow's simpler approach of recency-windowed truncation with explicit budget control achieved SOTA results on GAIA (82.4%). This suggests FormicOS's memory system may be over-engineered for its current scale (N ≤ 5 agents, R ≤ 15 rounds), and that a simpler recency window should be the default, with the full hierarchical system as an opt-in for long-running colonies.

MiroFlow's **robust workflow execution** — built-in handling for rate-limited APIs, unstable networks, and fault-tolerant concurrency for large-scale trajectory collection — highlights a gap in FormicOS's current specification. FormicOS has per-agent fault isolation (timeout/catch per agent in DAG execution) and crash-safe persistence (atomic write-fsync-replace), but lacks explicit retry strategies for transient LLM endpoint failures, backpressure handling for shared inference queues, and graceful degradation when VRAM is overcommitted across colonies. MiroFlow's production hardening is a maturity target.

MiroFlow's use of both **function calling and MCP** as complementary tool invocation mechanisms — structured API calls for standardized tool use, MCP for flexible context negotiation — maps directly onto FormicOS's dual-source tool call extraction (structured API response + XML regex fallback) and MCP gateway. But MiroFlow treats these as first-class training signals (agentic trajectories are synthesized using both paradigms for diversity), while FormicOS treats them as runtime fallbacks. If FormicOS trains or fine-tunes local models for agent use (as MiroThinker does with agentic RL), the training data should include both invocation styles.

### What OmniGAIA reveals

OmniGAIA introduces a benchmark for agents that must jointly reason over **video, audio, and image** inputs while using external tools. Its companion agent, **OmniAtlas**, extends a base LLM with **active perception tools** — the agent can request and examine additional media segments during multi-step reasoning, rather than receiving all modality data upfront.

FormicOS is currently text-only. The formal specification, the Context Tree, the DyTopo routing system, and the tool dispatch table all assume string inputs and outputs. OmniGAIA demonstrates that the next generation of agent tasks will require cross-modal reasoning as a baseline capability, not an extension.

The architectural implication for FormicOS is threefold:

First, the **tool dispatch table** needs media-handling tools. OmniGAIA agents use tools for video segment extraction, audio transcription, image analysis, web search, and code execution. FormicOS's current five built-in tools (file_read, file_write, file_delete, code_execute, qdrant_search) plus MCP fallback are sufficient for text-and-code workflows, but a colony tasked with analyzing a video tutorial or a podcast would need perception tools either as built-in dispatch entries or as MCP-served capabilities. The MCP gateway architecture already supports this — no core changes needed, just tool registration.

Second, the **TKG (temporal knowledge graph)** should support typed entities. OmniGAIA's omni-modal event graph links entities across modalities — a person mentioned in audio, visible in video, and named in text. FormicOS's TKG stores (subject, predicate, object, round, timestamp) tuples as strings. Adding a modality tag or entity type field would let the TKG represent cross-modal knowledge without changing the hash-indexed storage structure or the O(1) subject lookup.

Third, OmniGAIA's **active perception** pattern — where the agent decides *what additional data to request* during reasoning, rather than receiving everything at the start — reinforces FormicOS's tool-use loop design (Algorithm 3a). An agent that can call `extract_video_segment(timestamp_start, timestamp_end)` mid-reasoning is structurally identical to an agent that calls `file_read(path)` mid-reasoning. The bounded reactive planning loop (up to 10 LLM calls per agent per round) already supports this interaction pattern. The constraint is tool availability, not architecture. (OmniGAIA demonstrates that the next generation of agent tasks will require cross-modal reasoning. FormicOS's Dockling Perception Layer already normalizes visual PDFs into Markdown, but full audio/video active perception will require expanding the MCP tool registry.)

OmniGAIA's **hindsight-guided tree exploration** training strategy — where failed agent trajectories are analyzed to produce improved training data — is a training-time analog of FormicOS's runtime SkillBank. Both systems extract lessons from failures and make them available for future attempts. OmniGAIA does this through DPO fine-tuning on the model weights; FormicOS does it through distilled heuristics injected into agent context at runtime. These are complementary: a FormicOS deployment using a model fine-tuned with OmniGAIA-style hindsight data would benefit from both learned behavioral patterns (in the weights) and accumulated situational knowledge (in the SkillBank).

---

## Infrastructure

FormicOS operates defensively as a bare-metal orchestrator using the "Sibling Container" paradigm. While the baseline deployment is managed via `docker-compose`, the architecture bypasses nested virtualization traps. The orchestrator (FastAPI + Web Dashboard), a pure-async DyTopo router, and a cryptographic `EgressProxy` run on the Host network alongside local Qdrant and `vLLM` servers.

To prevent container escapes while executing untrusted payloads, FormicOS utilizes `gVisor` (runsc). When a sub-agent is spawned, the Orchestrator invokes the host's Docker socket to spin up an unprivileged, micro-sandboxed sibling container completely air-gapped from the host network, guaranteeing zero-trust isolation. 

The system targets a single consumer GPU (e.g., RTX 4090 or RTX 5090) as its baseline deployment. FormicOS relies on `vLLM`'s continuous PagedAttention batching, caching the massive system prompt once in VRAM and dynamically sharing the KV cache blocks across potentially hundreds of simultaneous, unprivileged sub-agent queries.

The web dashboard provides a supercolony overview, live REPL telemetry streaming, agent logic expansion, and an integrated settings UI to dynamically switch models and system rules during flight.

---

## What FormicOS is for

FormicOS is designed for a user who has local GPU hardware and wants multi-agent collaboration on sustained, multi-round tasks — code generation and refactoring, document organization and analysis, research synthesis, test generation — with full privacy, no mandatory cloud dependency, and the ability to pause, resume, and learn across task sessions.

It is not designed for single-turn question answering, real-time chat, or tasks that complete in one LLM call. The overhead of topology construction, multi-agent execution, and governance monitoring is justified only when the problem benefits from multiple perspectives, iterative refinement, or specialized agent roles working in coordination.

---

## Key design choices and their justifications

**Why cosine similarity routing instead of LLM-based dispatch.** Embedding 8–10 short descriptors with MiniLM takes ~20ms on CPU. An LLM call to decide routing would take 5–15 seconds and consume tokens from the context budget. The routing quality depends on descriptor quality, not routing model sophistication. MiroFlow's agent graph approach uses LLM-level planning for sub-agent dispatch, which is more flexible but slower; FormicOS optimizes for per-round latency at the cost of routing expressiveness.

**Why fixed castes instead of dynamic role assignment.** Each caste (Manager, Architect, Coder, Reviewer, Researcher, Tester, Designer) has a system prompt and tool allowlist. Roles are assigned at colony creation, not discovered at runtime. This is less flexible than MiroFlow's sub-agent spawning or OmniGAIA's active tool discovery, but it makes the system debuggable: you can predict which agent will have which tools, and audit which caste produced which output.

**Why a skill library instead of fine-tuning.** FormicOS distills reusable heuristics from completed colonies and injects them into future agents' context at runtime. This works with any base model and accumulates knowledge without training infrastructure. OmniGAIA's hindsight-guided DPO and MiroFlow's agentic RL training pipelines produce stronger behavioral patterns, but require GPU-hours for training, training data pipelines, and model versioning. The SkillBank is a zero-training-cost alternative that produces diminishing but genuine returns, suitable for a local deployment where the user doesn't have a training cluster.

**Why single-GPU by default.** The target user has one workstation with one consumer GPU. Multi-GPU setups, tensor parallelism, and distributed inference are supported via the model registry (which can point to any OpenAI-compatible endpoint), but the default configuration assumes a single-card setup. MiroFlow's demonstration of SOTA agent performance on a single RTX 4090 with MiroThinker validates this constraint.
