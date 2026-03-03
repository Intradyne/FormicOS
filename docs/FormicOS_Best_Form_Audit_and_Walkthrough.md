# FormicOS: The Best Form — Assumption Audit & Usage Narrative

> A ground-truth review of the formal algorithmic spec, followed by a dense walkthrough of how a real user actually interacts with a Supercolony deployment across multiple colonies.

---

## Part 1: Assumption Audit of the Formal Spec

The formal algorithmic specification is structurally sound. The math checks out, the invariants hold, and the complexity analysis is accurate. But there are several places where the formal spec and the v0.5.0 architecture spec disagree, where defaults carry hidden assumptions, or where the formalism glosses over implementation reality. Here's what I found.

### What's correct and well-specified

**The outer loop (Algorithm 1: ORCHESTRATE)** correctly models a fixed-point iteration with a mutable upper bound. The while-not-for insight is right — `extend_rounds(n)` only increases R, preserving the termination guarantee. The five disjunctive termination conditions are exhaustive.

**DyTopo (Algorithm 2)** is mathematically clean. The edge direction convention — `S[i,j] = cos(q_i, k_j)`, with `A[i,j] = 1` meaning "j sends to i" — matches the DyTopo paper and the deep implementation reference exactly. The greedy cycle-breaking terminates because it removes exactly one edge per iteration from a finite set. Kahn's topological sort is the right choice (deterministic tiebreaking by agent ID is implied but should be stated). The fallback table (broadcast for round 0, chain for zero edges) is correct.

**DAG execution (Algorithm 3)** correctly specifies topological-order scheduling with per-agent fault isolation. The dual-source tool call extraction (structured API response OR XML regex fallback) matches the llama.cpp reality — local models sometimes emit tool calls as XML in content rather than in the structured `tool_calls` field.

**Governance (Algorithm 5)** — all three monitors are independent and well-defined. The total order on severity actions (`continue < intervene < warn < force_halt`) with max-severity selection is elegant and correct. The convergence streak counter is essentially a discretized CUSUM test.

**The concurrency model (Section 7)** is the strongest section. The single-lock justification (snapshot consistency requires all scopes simultaneously; per-scope locks create deadlock risk) is a real insight. The TTL-based file locks with correctness-for-liveness tradeoff is the right call for agents that mostly operate on separate files. Colony isolation via independent AsyncContextTree instances is clean.

### Discrepancies with v0.5.0 architecture spec

**Context Tree scopes: 4 vs 6.** The formal spec's notation section defines `C` as `(scope, key) -> value` but never enumerates scopes. The ASSEMBLE_CONTEXT algorithm (Section 4) lists 7 priority sections but doesn't name them as formal scopes. The v0.5.0 architecture spec defines **six explicit scopes**: SUPERCOLONY, SYSTEM, PROJECT, COLONY, KNOWLEDGE, and RAG. The formal spec's context assembly mixes scope data (system info, project structure, colony state) with derived data (skills, feedback) without making this distinction. This isn't wrong, but it means the formal spec and the implementation spec aren't aligned on what "scope" means.

**Embedding dimension D = 384 is only half the story.** The formal spec fixes D = 384 (MiniLM-L6-v2) and uses it throughout. But the v0.5.0 spec uses **two embedding models**: MiniLM-L6-v2 at D=384 for DyTopo routing, and BGE-M3 at D=1024 for RAG/semantic search. The formal spec's SkillBank retrieval (Algorithm 6) uses `phi(x)` for cosine search — but which embedding model? If skills are stored with MiniLM embeddings (fast, 384-dim) they can't be compared against RAG queries using BGE-M3 (1024-dim). The v0.5.0 spec implies skills use the routing embedder (MiniLM), which makes sense since skill retrieval happens at orchestration time alongside DyTopo, but the formal spec should state this explicitly.

**Colony state machine mismatch.** The formal spec defines: `{CREATED, READY, RUNNING, PAUSED, COMPLETED, FAILED}` with `CREATED -> {READY, RUNNING}`. The v0.5.0 spec adds a **CONFIGURING** state between CREATED and READY, which is where the operator assigns castes, models, and tools via the dashboard. This is a meaningful state — a colony with no agents configured can't transition to READY. The formal spec skips it.

**No SUPERCOLONY scope in the formal spec.** The entire Supercolony management layer (ColonyManager, Model Registry, VRAM scheduling, cross-colony KNOWLEDGE scope) is described in v0.5.0 but absent from the formal spec. Algorithm 1 takes a single colony's inputs and produces a single colony's outputs. The formal spec models one colony at a time and gestures at cross-colony skill transfer (Algorithm 6) without specifying how the ColonyManager coordinates VRAM, multiplexes WebSocket streams, or manages the shared Model Registry.

### Hidden assumptions in the defaults

**tau = 0.35 assumes MiniLM-L6-v2 specifically.** The DyTopo deep implementation reference notes that useful key-query pairs score 0.4–0.8 on MiniLM, while noise pairs score 0.05–0.25. The 0.35 threshold sits between these ranges. If you swap in a different embedding model (like snowflake-arctic-embed-xs, which the stack reference suggests as a drop-in upgrade), the similarity distribution shifts and tau may need recalibration. The formal spec treats tau as a free parameter but defaults to 0.35 without stating the model dependency.

**k_in = 3 is sized for N ≤ 5 agents.** With 5 agents, k_in = 3 means each agent can receive messages from at most 60% of others. This is reasonable. At N = 10, k_in = 3 means each agent sees at most 30% of peers — potentially too restrictive for collaborative tasks. At N = 3, k_in = 3 means no filtering at all (it's a complete graph minus self-loops). The formal spec doesn't discuss how k_in should scale with N.

**theta_conv = 0.95 is conservative but correct.** The v0.5.0 spec and the deep implementation reference both confirm this: incremental progress produces round-summary similarity of ~0.7–0.9, while true stalls hit >0.95. The H_halt = 2 streak requirement means you need 3 consecutive similar rounds (the initial + 2 more) before force-halting. This is appropriately conservative.

**MAX_ITERATIONS = 10 for the inner tool-use loop.** This bounds each agent's reactive planning to 10 LLM calls. At 5–15 seconds per call on local inference (Qwen3-30B at 110 tok/s), that's 50–150 seconds worst case per agent per round. With 5 agents in topological order, a single round could take 4–12 minutes if every agent maxes out its tool loop. The formal spec states this bound but doesn't discuss timeout coordination with the outer loop or HITL approval gates (which have their own 5-minute timeout).

**TKG cap at 5000 tuples with FIFO eviction.** The formal spec states this as the max, with subject-keyed hash map for O(1) lookup. This is fine for single colonies, but the v0.5.0 spec's SUPERCOLONY scope implies TKG data might be shared or aggregated across colonies. The formal spec doesn't address cross-colony TKG.

### Things the formal spec gets right that the architecture spec doesn't formalize

**The persistence guarantee** — atomic write-fsync-replace — is precisely specified in the formal spec and only gestured at in the architecture spec ("JSON file per session"). The formal spec's crash-safety argument (either old complete file or new complete file survives) is correct and important.

**The recovery protocol** — downgrading RUNNING colonies to PAUSED on startup — is a clean safety mechanism that the architecture spec mentions but doesn't formalize.

**The SkillBank evolution cycle** — EMA success correlation, periodic pruning of zero-retrieval skills, flagging low-performing high-retrieval skills — is more precisely specified in the formal spec than in the architecture spec's prose description.

### Minor issues

The formal spec uses `G` for both the TKG tuple set (Section 1 notation) and the topology graph (Algorithm 1, `G_r`). These are different structures. The topology should use a different symbol.

The `AGENT_EXECUTE` algorithm specifies `ENFORCE_TOKEN_BUDGET` but doesn't describe the truncation strategy. The architecture spec says greedy bin-packing by priority section — the formal spec should reference this.

The `PARSE_DESCRIPTOR` function at the end of AGENT_EXECUTE is mentioned but never defined. This is where the agent's response gets split into (approach, alternatives, output) — a critical step for the path-diversity governance monitor.

---

## Part 2: The Best Form of FormicOS — From First Launch Through Multi-Colony Use

What follows is a dense, concrete walkthrough of how a user actually operates FormicOS, told through a scenario with three colonies that demonstrates every major subsystem.

### First launch: What the user sees

You've got an RTX 5090 (32 GB VRAM), a local Obsidian vault full of personal notes, and a codebase you want to refactor. You clone the FormicOS repo, and your first interaction is `docker-compose up`.

Four containers start: **formicos** (the FastAPI orchestrator + web dashboard), **llm** (llama.cpp serving Qwen3-30B-A3B-Instruct-2507 in Q4_K_M quantization, ~25.6 GB VRAM, launched with `--jinja -fa --ctx-size 8192`), **embedding** (llama.cpp serving BGE-M3 Q8_0 for RAG, ~1.2 GB VRAM, `--embeddings --ctx-size 2048`), and **qdrant** (vector database, CPU-only, ~2 GB RAM). The `--jinja` flag on the LLM container is critical — without it, tool calls fail silently. Flash attention (`-fa`) is on by default in recent builds but you want it explicit.

Inside the formicos container, two more things initialize lazily: **MiniLM-L6-v2** loads into CPU RAM (~500 MB) via SentenceTransformers the first time DyTopo routing runs, and the **watchdog filesystem observer** (stigmergy.py) starts monitoring workspace directories for file changes.

You open `http://localhost:8000` and see the **Supercolony Overview Panel** — an empty dashboard showing no colonies, the Model Registry with your two local backends registered (`local/qwen3-30b` at 25.6 GB, `local/bge-m3` at 1.2 GB), and VRAM status showing ~5.2 GB free. The SkillBank is empty. The KNOWLEDGE scope has no success patterns.

This is the Supercolony: the top-level entity that manages all your colonies, tracks available models, and holds the shared skill library.

### Colony 1: "notes-organize" — Personal knowledge management

You click "New Colony" in the dashboard. The colony creation wizard asks for a task description, agent configuration, and workspace path.

**Task:** "Organize my Obsidian vault: identify thematic clusters across my notes on AI architecture, extract key decisions and their justifications, and produce a structured index with cross-references."

**Agents you configure:**

| Agent ID | Caste | Model | Purpose |
|----------|-------|-------|---------|
| manager_01 | Manager | local/qwen3-30b | Goal-setting and termination |
| researcher_01 | Researcher | local/qwen3-30b | Reads notes, finds patterns |
| architect_01 | Architect | local/qwen3-30b | Designs the index structure |
| designer_01 | Designer | local/qwen3-30b | Writes the actual index files |

**Workspace:** `./workspace/notes-organize/`

You copy (or symlink) your Obsidian vault into this workspace. The stigmergy watcher detects the new files and populates the PROJECT scope's `file_index` with every markdown file and its path.

You also ingest key notes into Qdrant via the `/api/rag/ingest_file` endpoint — this creates embeddings using BGE-M3 (1024-dim) and stores them in the `colony_notes_organize` namespace. This is the RAG scope: semantic search over your documents.

**You hit "Start Colony."**

The colony transitions: **CREATED → CONFIGURING → READY → RUNNING**.

#### Round 0: The broadcast round

The ORCHESTRATE algorithm (Algorithm 1) enters its first iteration with `r = 0`.

Phase 1 — **MANAGER_GOAL**: The manager agent receives the full task description and produces the first round goal: "Survey the vault and identify the top 5 thematic clusters by reading representative files from each apparent topic area."

Phase 2–3 — Since `r = 0`, the topology is **BROADCAST**: all four workers execute in parallel with no edges. This is the formal spec's fallback for round 0 — no history exists, so agents can't generate meaningful descriptors yet.

Phase 3.5 — **Skill retrieval**: The SkillBank is empty (first colony ever), so `sigma = []`. No skills injected.

Phase 4 — **DAG_EXECUTE**: All agents run simultaneously in topological order (which is arbitrary when there are no edges). Each agent gets the task, the goal, and its caste-specific system prompt. The researcher uses `qdrant_search` and `file_read` tools to scan notes. The architect reads the file index. The designer reads representative files. Each agent's inner tool-use loop (Algorithm 3a) fires 2–4 LLM calls: initial response, tool call, tool result, final response. Each call takes 5–15 seconds on Qwen3-30B at 110 tok/s. Total round time: ~30–60 seconds (agents run in parallel when there are no dependency edges, but they share a single LLM endpoint, so they're effectively serialized through the inference queue).

Phase 5 — **Compression + Governance**: The archivist compresses all agent outputs into a 1–2 sentence episode summary. The TKG extractor pulls knowledge triples: ("vault", "contains_cluster", "AI architecture decisions"), ("vault", "contains_cluster", "prompt engineering patterns"), etc. The convergence monitor has no previous embedding to compare against (`v_prev = nil`), so it returns CONTINUE.

The round history H now has one entry.

#### Rounds 1–2: DyTopo routing kicks in

Round 1 begins. Now `r > 0`, so the system enters the full DyTopo pipeline.

**Intent declaration**: Each agent generates a (key, query) descriptor pair. For example:
- **researcher_01** — Key: "I have identified 5 thematic clusters with representative file lists." Query: "I need guidance on how to structure the cross-reference index."
- **architect_01** — Key: "I can design hierarchical index structures with bidirectional links." Query: "I need the thematic clusters and their representative files."

**DyTopo routing (Algorithm 2)**: MiniLM-L6-v2 encodes all 8 descriptors (4 keys + 4 queries) — ~20ms on CPU. The similarity matrix `S` is computed via a single matmul: `Q @ K.T` in R^{4×4}. Self-loops zeroed. Threshold applied at tau = 0.35. In-degree capped at k_in = 3.

The result: researcher_01 → architect_01 (the architect needs the researcher's clusters), architect_01 → designer_01 (the designer needs the architect's structure). The manager is typically isolated or receives from the researcher. Cycle check via DFS finds no cycles. Kahn's topological sort produces: `[researcher_01, architect_01, designer_01, manager_01]`.

**DAG execution**: Agents now execute in this order. The researcher runs first, its output becomes an upstream message to the architect. The architect runs next, receiving the researcher's clusters, and produces an index structure. The designer receives the architect's output and writes actual markdown files to the workspace.

**HITL gate**: When the designer calls `file_write` to create the index, a WebSocket approval modal pops up in the dashboard. You review the proposed file, click approve (or the 5-minute timeout auto-denies). This is the human-in-the-loop system — certain tools (file_write, file_delete, code_execute) require explicit approval.

By round 2, the outputs are stabilizing. The governance monitor computes cosine similarity between round 1 and round 2 summary embeddings: `cos(v_1, v_2) = 0.87`. Below theta_conv = 0.95, so the streak counter stays at 0. The path-diversity monitor checks that agents are exploring different approaches — researcher is scanning, architect is structuring, designer is writing. Diversity > 1, so no tunnel vision warning.

#### Rounds 3–4: Convergence and completion

By round 3, the researcher has covered all clusters, the architect's structure hasn't changed, and the designer is making only minor edits. The round summary embedding similarity hits 0.96 — above theta_conv. Streak counter increments to 1. The governance monitor returns INTERVENE (approaching convergence).

Round 4: similarity is 0.97. Streak hits 2, equaling H_halt. Governance returns **FORCE_HALT("Converged for 2 rounds")**. Alternatively, the manager might have already set `terminate = true` in its goal-setting phase, recognizing the task is done.

The colony transitions to **COMPLETED**.

#### Post-colony: Skill distillation

Algorithm 6 kicks in. The archivist reviews the full round history and distills skills:

- **General skill**: "When organizing a large document collection, identify thematic clusters first, then design the index structure, then write the cross-references. Don't try to do all three simultaneously."
- **Task-specific skill** (category: "knowledge-management"): "For Obsidian vaults, use bidirectional `[[wikilinks]]` in the index rather than flat markdown links — they integrate with Obsidian's graph view."
- **Failure lesson**: (none — this colony succeeded smoothly)

Each skill gets embedded with MiniLM-L6-v2 (phi function, D=384), checked against the SkillBank for deduplication (theta_dedup = 0.85), and stored. The SkillBank now has 2 entries.

---

### Colony 2: "api-refactor" — Code project pulling from Colony 1

You want to refactor a FastAPI backend. The code lives in a git repo. But you also want the agents to have access to the architecture decisions your first colony indexed from your notes — specifically the folder your notes-organize colony produced with the structured index.

**Creating the colony:**

Task: "Refactor the authentication module in the FastAPI backend to use OAuth2 with PKCE. Follow the architecture decisions documented in the imported notes index."

Agents:

| Agent ID | Caste | Model | Purpose |
|----------|-------|-------|---------|
| manager_01 | Manager | local/qwen3-30b | Goal-setting |
| architect_01 | Architect | local/qwen3-30b | Designs the refactored auth module |
| coder_01 | Coder | local/qwen3-30b | Writes implementation code |
| coder_02 | Coder | local/qwen3-30b | Writes tests |
| reviewer_01 | Reviewer | cloud/claude-sonnet-4-5 | Reviews code quality |

Workspace: `./workspace/api-refactor/`

**Pulling from Colony 1**: You copy the structured index folder from `./workspace/notes-organize/output/` into `./workspace/api-refactor/docs/architecture-notes/`. This is a filesystem-level operation — colonies are sandboxed, so you manually bridge them. The stigmergy watcher in colony 2 picks up these files and indexes them in the PROJECT scope. You also ingest them into Qdrant under the `colony_api_refactor` namespace for RAG search.

The key insight: **colonies don't share workspaces, but they share the KNOWLEDGE scope (SkillBank) and you can manually copy files between workspaces.** Colony isolation is a feature, not a limitation — it prevents one colony's file mutations from corrupting another's state.

**Notice the reviewer uses cloud/claude-sonnet-4-5.** This is the Model Registry at work — the heterogeneous model system from v0.5.0. When reviewer_01 runs, the orchestrator dispatches its LLM call to the Anthropic API instead of local llama.cpp. Because the model registry entry has `requires_approval: true`, a HITL approval modal fires the first time a cloud call is made (cloud burst approval).

**Round 0: Broadcast.** All 5 agents explore the codebase independently. The architect reads the imported architecture notes. The coders scan the existing auth module. The reviewer reads the test suite.

**Round 1: DyTopo routing with 5 agents.** The similarity matrix is now 5×5. With k_in = 3, each agent can receive from at most 3 peers. The typical topology: architect → coder_01 (implementation needs design), architect → coder_02 (tests need design), coder_01 → reviewer_01 (review needs implementation). The researcher caste is absent — no one's doing external research this time. Isolated agents (those with no matching intents) execute independently.

**Skill injection**: Now the SkillBank has 2 skills from Colony 1. At Phase 3.5, the orchestrator queries `SKILL_RETRIEVE(B, g_r, k=3)`. The round goal mentions "organizing module structure" — the general skill about "identify clusters first, then design structure" has a cosine similarity of ~0.42 against this goal. Above tau? Above the retrieval threshold. It gets injected as `[STRATEGIC GUIDANCE]` in each agent's context. The knowledge-management-specific skill about Obsidian wikilinks scores lower (~0.15) and isn't retrieved — correct, since this is a code task, not a notes task.

**This is cross-colony skill transfer.** Colony 1's hard-won lesson about organizing complexity (cluster → structure → implement) informs Colony 2's code refactoring approach without any explicit user intervention. The SkillBank's brute-force k-NN cosine search (O(|B| * D)) handles this in microseconds for |B| = 2.

**Rounds 2–5: The coding loop.** The caste system shines here. The architect produces a module design with clear interfaces. Coder_01 implements the OAuth2 flow — its inner tool-use loop (Algorithm 3a) involves: read file → write code → execute tests → read error → fix code → re-run tests. Up to 10 iterations of this, bounded by MAX_ITERATIONS. Coder_02 writes integration tests in parallel (after the architect, before the reviewer in topological order). The reviewer catches issues and its feedback feeds back through the round history for the next round.

**Stall detection kicks in at round 4.** The TKG contains triples like ("coder_01", "failed_test", "redirect_uri_validation") appearing 3 times. The stall detector (Algorithm 5c) finds this pattern: `|tuples| >= theta_stall (3)`. It generates a StallReport. The governance system escalates to WARN, and the manager adjusts its next round goal to focus specifically on redirect URI handling.

**Epoch compression**: By round 5, we have 5 episodes in the episode list. MAYBE_COMPRESS_EPOCH fires (window W_epoch = 5). The LLM compresses rounds 0–4 into a single paragraph epoch summary (~400 tokens). Now the context assembly for round 5+ includes the epoch summary instead of all 5 individual episode summaries — dramatically reducing token usage.

The colony completes at round 7. The manager sets `terminate = true` after all tests pass.

**Post-colony skills distilled:**
- **General skill**: "When refactoring authentication, start with the data model and token validation before touching the API endpoints."
- **Task-specific skill** (category: "fastapi-auth"): "For FastAPI OAuth2 with PKCE, use `authlib` for the PKCE flow and validate `code_verifier` server-side before issuing tokens."
- **Failure lesson**: "redirect_uri validation stalled for 3 rounds because the test fixture used `http://localhost` but the code required HTTPS. Always align test fixtures with production constraints."

SkillBank now has 5 entries. The evolutionary pruning cycle hasn't triggered yet (it runs every 5 completed colonies, and we've only done 2).

---

### Colony 3: "docs-rewrite" — Reusing lessons from both prior colonies

Now you want to rewrite your project's documentation. You want the docs to reflect the refactored auth module (Colony 2's output) and follow the organizational structure that Colony 1 discovered.

**Task:** "Rewrite the project documentation to cover the refactored OAuth2 authentication module. Use clear thematic organization with cross-references."

**Agents:**

| Agent ID | Caste | Model | Purpose |
|----------|-------|-------|---------|
| manager_01 | Manager | local/qwen3-30b | Goal-setting |
| researcher_01 | Researcher | local/qwen3-30b | Reads the codebase and existing docs |
| designer_01 | Designer | local/qwen3-30b | Writes the documentation |
| reviewer_01 | Reviewer | local/qwen3-30b | Reviews for clarity and completeness |

**Workspace:** `./workspace/docs-rewrite/`

You copy two things in: the refactored auth module code from Colony 2 (`./workspace/api-refactor/src/auth/`), and the organizational index from Colony 1 (`./workspace/notes-organize/output/index.md`). Again, manual workspace bridging.

**Round 0: Broadcast as always.**

**Round 1: Skill injection is now richer.** The SkillBank has 5 skills. The orchestrator queries with the round goal "Write clear, cross-referenced documentation for the OAuth2 module." Multiple skills fire:

- Colony 1's general skill about cluster-then-structure-then-implement: similarity ~0.48 → **retrieved**
- Colony 1's Obsidian wikilinks skill: similarity ~0.22 → not retrieved (this isn't an Obsidian project)
- Colony 2's general skill about starting with data models: similarity ~0.38 → **retrieved**
- Colony 2's FastAPI-specific skill about authlib: similarity ~0.51 → **retrieved** (directly relevant — the docs need to describe this)
- Colony 2's failure lesson about test fixtures: similarity ~0.19 → not retrieved (not relevant to documentation)

Three skills injected. The designer agent now knows to organize docs thematically (Colony 1), to start with the data model documentation (Colony 2), and to specifically document the authlib PKCE flow (Colony 2). This is **compound cross-colony skill transfer** — two prior colonies' distilled experience informing a third colony's work, with relevance filtering handled automatically by cosine similarity.

**This colony runs for 4 rounds** and completes. The documentation is structured, accurate, and covers the auth module thoroughly.

**Post-colony distillation adds 2 more skills.** SkillBank now has 7 entries. Each skill's `retrieval_count` is updated — the three skills that were used in Colony 3 now have retrieval_count >= 1, making them safe from the "zero-retrieval pruning" in the evolutionary cycle.

---

### Revisiting Colony 1: Resume and extend

Two weeks later, you've added more notes to your vault. You want Colony 1 to re-index.

You go to the Supercolony Overview Panel. Colony "notes-organize" shows status: **COMPLETED**. You click "Resume" — but COMPLETED is a terminal state, so FormicOS offers to **create a new colony** from the completed colony's configuration, pre-populated with the same agents, workspace, and RAG namespace. This is effectively "continuing" the work.

The new colony — "notes-organize-v2" — starts with an empty round history but inherits:
- The workspace files from the original colony (they're still in `./workspace/notes-organize/`)
- The RAG collection (documents already indexed in Qdrant under `colony_notes_organize`)
- The SkillBank entries (which are cross-colony by design — they live in the SUPERCOLONY scope)

Now the SkillBank has 7 skills from 3 prior colonies. When this colony runs, it benefits from everything the system has learned. The general skill about "cluster first" is retrieved again (retrieval_count now 3). The failure lesson about redirect URIs isn't retrieved (irrelevant). The system is getting smarter over time — not through fine-tuning, but through distilled heuristic accumulation in the SkillBank.

---

### Revisiting Colony 2: Pausing, VRAM management, and resumption

You realize the api-refactor colony needs another pass — there's a new requirement for refresh token rotation. But you're also running a heavy local model for something else and VRAM is tight.

You **pause** Colony 2 via the dashboard. The colony transitions: RUNNING → PAUSED. The full context tree is serialized to JSON via atomic write-fsync-replace (the formal spec's persistence guarantee). The session file preserves: round counter (was at 7), round history (all 7 rounds compressed into epoch summaries), topology from the last round, agent descriptors, TKG triples. The Model Registry notes that the local/qwen3-30b slot can potentially be shared.

Later, when VRAM frees up, you **resume**. The colony transitions PAUSED → RUNNING. The context tree is deserialized. The orchestrator picks up at round 8 (or effectively round 0 of a continuation — the history is all in the epoch summaries). The new task amendment is set by the manager: "Add refresh token rotation to the existing OAuth2 implementation."

The critical thing: **the topology, the round history, and the convergence state all restore.** This isn't "starting over with old files" — it's genuine session continuity. If the system had crashed instead of being paused, the recovery protocol would have detected the RUNNING state on startup and downgraded to PAUSED automatically.

---

### The infrastructure underneath all of this

**Docker composition**: 4 containers (formicos, llm, embedding, qdrant). The LLM server must have `--jinja` enabled or tool calling breaks. Flash attention on both LLM and embedding containers. BGE-M3's context size should be 2048–4096, not 16384 (the training context is 8192, and your chunks are shorter). The embedding server needs the `--embeddings` flag.

**VRAM budget**: Qwen3-30B-A3B in Q4_K_M uses ~25.6 GB. BGE-M3 Q8_0 uses ~1.2 GB. Total: ~26.8 GB on a 32 GB card. MiniLM-L6-v2 runs on CPU (~500 MB RAM). Qdrant is CPU-only (~2 GB RAM). You have ~5 GB VRAM headroom for KV cache growth. If you try to run two local models simultaneously for a mixed-model colony, you'll need to partially offload one to CPU or use aggressive quantization.

**Qdrant**: Uses `query_points()` (not the removed `client.search()`). Each colony gets its own namespace: `colony_{id}_docs`. Named vectors with BGE-M3's 1024-dim dense vectors. If you want hybrid search (dense + sparse), you can add Qdrant's built-in BM25 (v1.16+) for the sparse component since llama.cpp doesn't support BGE-M3's sparse mode.

**FastAPI**: Uses the `lifespan` async context manager pattern, not the deprecated `@app.on_event("startup")`. The WebSocket at `/ws/stream` multiplexes updates from all active colonies with a `colony_id` field.

**Web dashboard**: Vanilla JS + HTMX + Cytoscape.js for the topology graph. No React, no build step. The glassmorphism design system in ~2000 lines of CSS. The dashboard is a monitoring tool, not a full application.

**MCP integration**: The `mcp_client.py` provides a gateway for tools that FormicOS agents don't have natively. If an agent calls a tool that doesn't match the built-in dispatch table (file_read, file_write, file_delete, code_execute, qdrant_search), the call falls through to the MCP gateway, which forwards it to a configured MCP server. This is how you'd connect external tools — web search, calendar, database queries — without modifying agent code.

---

### The formal algorithms in practice: A summary of what you just saw

| What the user experienced | Algorithm / Subsystem |
|---------------------------|-----------------------|
| Creating and configuring a colony | Colony state machine (CREATED → CONFIGURING → READY) |
| Round 0 broadcast execution | ORCHESTRATE's `if r = 0: BROADCAST_TOPOLOGY` |
| Agents discovering meaningful connections | DyTopo (Algorithm 2): embed, matmul, threshold, toposort |
| Agents executing in dependency order | DAG_EXECUTE (Algorithm 3): topological-order scheduling |
| Agents calling tools iteratively | AGENT_EXECUTE (Algorithm 3a): bounded reactive planning loop |
| Approving file writes in the dashboard | HITL approval gate within AGENT_EXECUTE |
| Round summaries getting compressed | SUMMARIZE + MAYBE_COMPRESS_EPOCH (Algorithm 4) |
| Colony recognizing it's done | Convergence detection (Algorithm 5a): cosine streak counter |
| Detecting the redirect_uri stall | Stall detection (Algorithm 5c): frequent pattern mining on TKG |
| Skills from Colony 1 informing Colony 2 | SKILL_RETRIEVE (Algorithm 6b): brute-force k-NN cosine |
| Colony 3 benefiting from both prior colonies | Compound skill retrieval with relevance filtering |
| Pausing and resuming mid-work | Atomic write-fsync-replace persistence + state machine transitions |
| Two colonies not corrupting each other | Colony isolation via independent AsyncContextTree instances |
| Unused skills getting pruned after 5 colonies | EVOLVE (Algorithm 6c): zero-retrieval pruning + EMA correlation |

The system gets meaningfully better at each colony. Not through weight updates or fine-tuning, but through the SkillBank's evolutionary accumulation of distilled heuristics, filtered by semantic relevance at retrieval time and pruned by fitness over time. It's biological — not in a hand-wavy metaphorical sense, but in the specific sense that ant colonies get better at foraging through pheromone trail reinforcement (stigmergy) rather than individual learning. Skills are FormicOS's pheromone trails.
