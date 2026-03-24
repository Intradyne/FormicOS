# Research Prompt: Deploying FormicOS Wave 48 with NemoClaw + NeuroStack

## What I'm trying to build

A local-first AI development workstation that combines three systems:

1. **FormicOS** -- my multi-agent colony framework (event-sourced, stigmergic
   coordination, active web foraging, operator-editable knowledge,
   surgical code editing, git tools, fast_path for simple tasks)
2. **NVIDIA NemoClaw / OpenShell** -- NVIDIA's new open-source agent runtime
   with policy-based security sandboxing, privacy router for local/cloud
   model routing, Nemotron open models
3. **NeuroStack** -- local-first MCP server for persistent knowledge vaults
   with tiered retrieval, semantic search, stale note detection, Hebbian
   co-occurrence learning

## My hardware

- **RTX 5090** (32 GB VRAM) -- primary inference GPU
- **RTX 3080** (10 GB VRAM) -- secondary GPU
- Running Windows with WSL2/Docker Desktop
- Cloud API keys for Anthropic and OpenAI as escalation targets

## Current FormicOS deployment

- Docker Compose: Qdrant (vector store) + FormicOS (Python/Starlette) +
  llama.cpp server (Qwen3-30B-A3B-Instruct Q4_K_M)
- SQLite WAL for event store
- Lit Web Components frontend
- Local Qwen3-30B on RTX 5090 as primary, cloud Claude/GPT as escalation
- The Forager subsystem handles web search + content extraction + admission

## What I need to learn

### Q1: How should NemoClaw's OpenShell relate to FormicOS's existing sandbox?

FormicOS already has sandbox_manager.py (628 lines) with Docker-based
container isolation, seccomp profiles, and strict egress through
EgressGateway. NemoClaw provides OpenShell with similar policy-based
sandboxing.

- Should FormicOS colonies execute inside OpenShell sandboxes instead of
  or alongside the existing Docker sandbox?
- Can OpenShell replace the current seccomp + namespace isolation, or is
  it an additional outer layer?
- How does OpenShell's network policy compare to FormicOS's EgressGateway?
  Are they complementary or redundant?
- What's the right architecture: FormicOS manages its own sandboxes inside
  an OpenShell-managed outer sandbox, or OpenShell wraps the entire
  FormicOS Docker Compose stack?

Search: "NemoClaw OpenShell architecture sandbox nesting", "OpenShell
Docker integration", "NemoClaw custom agent integration non-OpenClaw",
"OpenShell policy egress network"

### Q2: How should NemoClaw's privacy router work with FormicOS's LLMRouter?

FormicOS has an LLMRouter that routes between local Qwen3-30B and cloud
providers (Anthropic/OpenAI) based on caste, task complexity, budget,
and escalation policy. NemoClaw has a privacy router that routes between
local Nemotron models and cloud frontier models based on privacy policy.

- Should these be layered (FormicOS routes to "local" which is actually
  NemoClaw's privacy router)?
- Should NemoClaw's privacy router replace FormicOS's LLMRouter, or sit
  beneath it?
- Can NemoClaw's Nemotron models (e.g., nemotron-3-super-120b-a12b) run
  alongside FormicOS's Qwen3-30B on the same GPU setup?
- What's the VRAM budget for running both Nemotron and Qwen3 models?

Search: "NemoClaw privacy router API integration", "Nemotron model VRAM
requirements RTX 5090", "NemoClaw custom LLM backend", "OpenShell inference
provider configuration"

### Q3: How should NeuroStack relate to FormicOS's knowledge substrate?

FormicOS has its own knowledge base (Qdrant vector store, SQLite event
store, memory entries with confidence decay, source credibility, competing
hypotheses, operator pin/mute/invalidate). NeuroStack has its own knowledge
vault (SQLite + FTS5, tiered retrieval, Hebbian co-occurrence, stale note
detection).

- Should they be separate systems serving different purposes, or should
  one feed the other?
- Could NeuroStack serve as the operator's personal knowledge layer
  (cross-project, cross-session) while FormicOS manages per-workspace
  colony knowledge?
- Could NeuroStack's MCP server be registered as an MCP tool in FormicOS,
  letting the Researcher caste query the operator's personal vault?
- How does NeuroStack's tiered retrieval (triples -> summaries -> full)
  compare to FormicOS's Thompson Sampling retrieval with confidence
  tiers?
- Could NeuroStack's stale note detection complement FormicOS's confidence
  decay mechanism?

Search: "NeuroStack MCP integration agent framework", "NeuroStack tiered
retrieval architecture", "MCP server knowledge federation multi-agent",
"NeuroStack FormicOS integration"

### Q4: Optimal GPU allocation across the stack

With RTX 5090 (32GB) + RTX 3080 (10GB):

- What's the best model assignment? (e.g., Qwen3-30B on 5090, embedding
  model on 3080, NeuroStack's Ollama models on 3080?)
- Can Nemotron models fit on the 3080 as a secondary inference path?
- What's the VRAM budget breakdown for running:
  - Qwen3-30B-A3B Q4_K_M (~21 GB weights + KV cache on 5090)
  - Qdrant (CPU, no GPU needed)
  - NeuroStack's embedding model (on 3080?)
  - Nemotron-mini or similar (on 3080?)
  - FormicOS embedding sidecar (currently on 5090)
- Should the embedding models move to the 3080 to free 5090 for pure LLM?

Search: "RTX 5090 RTX 3080 multi-GPU inference setup", "Nemotron model
sizes VRAM requirements", "multi-GPU local inference llama.cpp vLLM SGLang",
"dual GPU model assignment AI workstation"

### Q5: Docker Compose orchestration for the combined stack

Currently FormicOS runs 3 Docker services: qdrant, formicos, llm. Adding
NemoClaw and NeuroStack means:

- What's the right Docker Compose topology?
- Does NemoClaw/OpenShell need to wrap the entire Compose stack, or can it
  be a service alongside?
- Where does NeuroStack's MCP server run (host-side? another container?)?
- How do the services discover each other?
- What's the startup order / dependency chain?
- Any volume sharing considerations (FormicOS workspace dir, NeuroStack
  vault dir, NemoClaw sandbox dir)?

Search: "NemoClaw Docker Compose integration", "NeuroStack Docker
deployment", "MCP server Docker container networking", "OpenShell Docker
nesting"

### Q6: What does "always-on" mean for this stack?

NemoClaw is designed for "always-on" agents. FormicOS currently runs
on-demand (operator submits tasks). NeuroStack can run as a background
watcher on the knowledge vault.

- Should FormicOS adopt an always-on posture, or stay on-demand with the
  maintenance briefing loop as the ambient layer?
- How does NemoClaw's always-on model interact with FormicOS's event-driven
  colony spawning?
- What's the power/resource cost of running this stack always-on on a
  desktop workstation?
- Is there a hybrid: NemoClaw always-on for monitoring, FormicOS spawns
  colonies on events, NeuroStack watches the vault?

Search: "NemoClaw always-on agent resource usage", "always-on AI agent
desktop workstation power", "event-driven vs always-on agent architecture",
"NemoClaw idle resource consumption"

### Q7: Security and trust model across the three systems

Each system has its own security model:
- FormicOS: EgressGateway domain allowlists, sandbox_manager with seccomp,
  BudgetEnforcer, operator approval for sensitive actions
- NemoClaw: OpenShell policy-based sandboxing, privacy router, operator
  approval TUI
- NeuroStack: local-first, files never modified, read-only vault access

- How do these trust models compose? Who is the authority?
- If NemoClaw's OpenShell blocks an egress request that FormicOS's
  EgressGateway would allow, which wins?
- Should FormicOS's operator approval surface integrate with NemoClaw's
  TUI, or stay separate?
- What's the credential/secret management story across all three?

Search: "NemoClaw OpenShell security policy composition", "multi-layer
agent sandboxing trust model", "NemoClaw operator approval integration"

## Output format

For each question:
1. What the current docs/community say (these are all very new tools)
2. Concrete recommended architecture
3. Docker Compose service layout recommendation
4. VRAM / resource budget estimate
5. What to try first vs what to defer

## My deployment priorities (in order)

1. FormicOS colonies can execute real coding tasks safely
2. Knowledge persists and transfers effectively across sessions
3. Cloud escalation works with proper privacy controls
4. The combined stack is debuggable and observable
5. Resource usage is reasonable for a desktop workstation

## What I do NOT need researched

- FormicOS internals (I built it)
- General multi-agent architecture
- LLM benchmarks or model comparisons
- Basic Docker or NVIDIA container setup
- NeuroStack vault management (I can learn that from their docs)

Focus on: **how these three specific systems should compose together
on my specific hardware for my specific use case (developer AI
workstation with persistent cross-project knowledge).**
