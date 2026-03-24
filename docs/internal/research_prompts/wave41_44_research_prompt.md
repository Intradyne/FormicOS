# Research Prompt: Production Deployment, Static Analysis, and System Hardening for a Multi-Agent AI Colony Framework (2025-2026)

## Context you have

You are a research agent with access to **web search** and **project knowledge** only. You do NOT have access to the FormicOS codebase. Your job is to produce a synthesis document that informs engineering decisions across four development waves:

- **Wave 41 ("The Capable Colony"):** Math bridges (trust weighting, TS/UCB unification, contradiction pipeline) + production capability (workspace executor, multi-language test execution, multi-file coordination, static code analysis, cost optimization). Mostly landed; loose ends being closed.
- **Wave 42 ("The Intelligent Colony"):** Evidence-gated second capability wave. Static code analysis tooling, belief-informed topology prior, contradiction resolution upgrade, adaptive evaporation, knowledge extraction quality improvement. Only upgrades with clear live seams and strong expected payoff.
- **Wave 43 ("The Hardened Colony"):** Docker deployment, container security, cold-start performance, regression testing, documentation truth pass, deployment readiness. The "make it run in production" wave.
- **Wave 44 ("The Proven Colony"):** Full-stack measurement, three public demos (live, benchmark, audit), compounding curve analysis, ablation, optional publication.

## What FormicOS is

FormicOS is an open-source (AGPLv3), local-first, event-sourced, multi-agent AI colony framework. Key facts for this research:

- **Tech stack:** Python 3.12+, Lit Web Components, SQLite WAL (event store), Qdrant (vector store), FastMCP, Starlette, Docker for sandboxed code execution.
- **Event-sourced:** 58 event types in a closed union. All truth is replay-derivable. Cold start replays from the event log.
- **Operator co-authorship:** Pin/mute/annotate/invalidate are first-class replayable events. Local-first editorial overlays that do NOT mutate shared confidence posteriors.
- **Multi-language execution:** Workspace executor runs shell commands (git, pytest, go test, cargo test, npm test, javac) in a working directory. Sandbox executor runs isolated Python in Docker containers with resource limits.
- **Colony coordination:** Queen coordinator plans tasks, delegates to parallel colony groups. DyTopo stigmergic routing builds agent communication graphs from embeddings and pheromone weights. Knowledge substrate with Thompson Sampling retrieval, co-occurrence reinforcement, Bayesian confidence with gamma decay.
- **Current Docker story:** `sandbox_manager.py` runs Python code in Docker containers with `--network=none`, memory limits, CPU limits, read-only filesystem, tmpfs. Falls back to subprocess when Docker is unavailable. A separate `execute_workspace_command()` runs shell commands in workspace directories without Docker isolation.
- **Static analysis (Wave 42):** Planning to add lightweight multi-language code structure analysis (imports, function inventory, file-type detection) as a workspace-scoped substrate. Not tree-sitter -- stdlib-based where possible, regex for other languages.
- **Test suite:** 168+ test files. CI with ruff, pyright, layer boundary lint, pytest. Playwright browser smoke tests.

The product thesis: **FormicOS is an editable shared brain with operator-visible traces, where every decision is inspectable, every assumption is editable, and every adaptation is reversible.**

## What to research

Search the project knowledge FIRST for every section. It contains extensive prior research on FormicOS architecture, multi-agent coordination, benchmarking, deployment, and the NVIDIA ecosystem. Use web search to fill gaps and find current (2025-2026) developments.

---

### Section 1: Docker Deployment Patterns for Multi-Agent AI Systems (Wave 43)

**Goal:** Inform the Docker hardening wave. FormicOS needs to run its full stack in containers reliably, securely, and with acceptable cold-start performance.

Research:

1. **Docker Compose patterns for event-sourced Python applications.** FormicOS needs at minimum: a backend container (Python 3.12+, Starlette), a vector store container (Qdrant), and sandbox containers for code execution. What are the current best practices for Docker Compose orchestration of event-sourced systems? How do production deployments handle event store recovery, projection rebuild on container restart, and health checking for event-sourced services? What patterns exist for SQLite WAL in containers (single-writer constraint, volume mount strategies, backup/snapshot)?

2. **Multi-language sandbox container design.** FormicOS's workspace executor needs to run tests across Python, Go, Rust, JavaScript/Node, Java, and C++. What are the current approaches to multi-language execution containers? Single fat image with all toolchains vs per-language sidecar images vs on-demand image pulls? What are the size/security/startup tradeoffs? How do Aider, Devin, OpenHands, and SWE-Agent handle multi-language execution environments? What base images do they use?

3. **Container security for AI agent code execution.** The colony executes arbitrary code from tasks. Current security: `--network=none`, memory limits, CPU limits, read-only filesystem, tmpfs. What additional security hardening do production AI coding agents use? gVisor/runsc vs standard runc? Seccomp profiles? AppArmor/SELinux? User namespace isolation? What's the threat model for an AI agent that clones and executes code from arbitrary Git repositories?

4. **Cold-start performance for event-sourced systems in containers.** FormicOS replays its event log on startup to rebuild projections. With 1,000+ events, how long should this take? What are the optimization patterns? Snapshots/checkpoints? Lazy projection loading? Blue-green projection rebuilds? How do production event-sourced systems (Axon Framework, EventStoreDB users, Marten) handle cold start in containerized deployments?

5. **Volume and state management for local-first AI frameworks.** FormicOS is local-first with SQLite WAL for events, Qdrant for vectors, and filesystem workspaces for colony execution. How should these be mounted in Docker? Named volumes vs bind mounts? What are the patterns for data persistence across container restarts? How do you handle Qdrant data directory in Docker Compose? What about workspace cleanup between task runs?

6. **Docker-in-Docker vs sibling containers for sandboxed execution.** FormicOS's backend container needs to launch sandbox containers. The current approach uses the host Docker socket. What are the security implications? What are the alternatives (Docker-in-Docker, Sysbox, Podman, rootless Docker)? How do CI/CD systems and coding agents handle this nested-container problem?

---

### Section 2: Lightweight Static Code Analysis for AI Agent Workspaces (Wave 42)

**Goal:** Inform the design of cheap, multi-language structural analysis that gives the colony code-structure knowledge without LLM token burn.

Research:

1. **Python AST-based code analysis tools.** FormicOS already uses Python `ast` for security scanning. What are the current lightweight tools for extracting import graphs, function/class inventories, and call graphs from Python code using `ast` alone (no external dependencies)? What's achievable in <100ms per file? How do tools like `pydeps`, `modulegraph`, and `importlib.metadata` compare?

2. **Multi-language import/dependency extraction without tree-sitter.** For JavaScript/TypeScript (import/require), Go (import blocks), Rust (use statements), Java (import statements), and C++ (include directives): what regex or lightweight parsing approaches provide 80%+ accuracy for import graph extraction? What edge cases break regex-based approaches (conditional imports, dynamic requires, build-system-generated imports)?

3. **Test-to-source file mapping heuristics.** For multi-language projects: what heuristics reliably map test files to source files? Naming conventions (`test_foo.py` -> `foo.py`, `foo.test.ts` -> `foo.ts`)? Directory structure mirroring (`tests/` -> `src/`)? Import analysis (test imports source)? What accuracy do these achieve on real-world repositories?

4. **Code structure as agent context: what helps and what hurts.** Research on providing code structure information to LLM agents for code editing tasks. Does import graph context improve multi-file edit success? Does function inventory context help? At what point does structural context become noise that hurts more than it helps? What's the optimal granularity (file-level, function-level, line-level)?

5. **Workspace-scoped structural indexes vs persistent knowledge.** For an AI agent working on a codebase: should structural facts (import graphs, call chains) be treated as ephemeral workspace context or as persistent learned knowledge? How do Cursor, Cody, and other AI code assistants handle codebase indexing? What's the re-indexing cost when files change during a task?

---

### Section 3: Production Hardening Patterns for AI Agent Frameworks (Wave 43)

**Goal:** Inform the security, reliability, and operational maturity work needed before public deployment.

Research:

1. **Security hardening for AI agent systems that execute code.** Beyond sandbox isolation: what are the production security patterns for AI agents that clone repositories, install dependencies, and run tests? Dependency supply chain attacks (malicious packages in requirements.txt)? Git clone security (malicious hooks, submodule attacks)? Filesystem escape attempts? Network exfiltration via test code? What do Devin, OpenHands, and enterprise coding agents do?

2. **Rate limiting and resource governance for multi-agent systems.** FormicOS runs multiple colonies potentially in parallel, each consuming LLM tokens, vector search queries, and compute. What are the production patterns for resource governance? Per-workspace budgets? Per-colony token caps? Backpressure mechanisms? How do multi-tenant AI platforms handle resource isolation between concurrent agent workloads?

3. **Observability and telemetry for event-sourced agent systems.** FormicOS has structlog-based logging and a JSONL telemetry adapter. What additional observability is needed for production? OpenTelemetry integration? Distributed tracing for colony execution? Metrics for event replay time, retrieval latency, LLM call duration? Dashboard patterns for multi-agent system health? What do production agent frameworks export?

4. **Automated regression testing for systems with LLM-dependent behavior.** FormicOS has 168+ test files, but many behaviors depend on LLM output which is non-deterministic. What are the current best practices for testing AI agent systems? Mocked LLM responses? Recorded/replayed interactions? Property-based testing of agent behavior? How do you write regression tests for a system where the "correct" behavior depends on model choice?

5. **Documentation standards for production open-source AI frameworks.** What does a credible production-ready open-source AI framework need beyond code docs? Deployment guides? Runbooks? Troubleshooting guides? Architecture decision records? Security advisories? Changelog standards? How does FormicOS's current documentation (CLAUDE.md, OPERATORS_GUIDE.md, KNOWLEDGE_LIFECYCLE.md, 49 ADRs, SECURITY.md, GOVERNANCE.md, CONTRIBUTING.md) compare to what LangChain, CrewAI, AutoGen, and OpenHands provide?

---

### Section 4: Compounding Curve Measurement and Publication Methodology (Wave 44)

**Goal:** Inform the design of a credible compounding-curve experiment and the potential publication of results.

Research:

1. **Sequential learning measurement in AI coding agents.** Has anyone measured whether AI coding agents improve on later tasks in a sequence because of accumulated knowledge from earlier tasks? ExpeRepair, Live-SWE-agent, and VOYAGER are known precedents from project knowledge. What additional 2025-2026 work exists? What experimental controls are needed to distinguish genuine learning from confounds (task ordering effects, model warm-up, prompt caching)?

2. **Statistical methodology for evaluating multi-agent AI systems.** Anthropic's "Adding Error Bars to Evals" is a known reference from project knowledge. What additional methodology guidance exists for: paired difference analysis on the same tasks, bootstrap confidence intervals for pass rates, handling variance from Thompson Sampling stochasticity, power analysis for detecting small (2-5 percentage point) improvements with limited task counts?

3. **Ablation study design for complex AI systems.** What's the minimum credible ablation for a system with 5+ interacting components (stigmergic topology, knowledge retrieval, pheromone reinforcement, trust weighting, adaptive evaporation)? LOCO (Leave-One-Component-Out) vs factorial vs sequential? How many configurations are needed? How do you handle the combinatorial explosion of interaction effects?

4. **Public demonstration design for AI agent systems.** What makes a compelling public demo of an AI agent framework? Live execution vs recorded? Failure handling (what happens when the demo fails live)? Audience-appropriate complexity? How do Devin demos, OpenHands showcases, and Google ADK presentations handle this? What resonates with developers vs enterprise buyers vs researchers?

5. **AI benchmark result presentation norms (2025-2026).** How should benchmark results be presented for credibility? What metadata is expected (model versions, temperatures, number of runs, cost, compute infrastructure)? How do you present results from a multi-agent system where "the model" is actually a colony configuration? What are the anti-patterns (cherry-picking, single-run reporting, unreported variance)?

---

### Section 5: NVIDIA and Cloud Ecosystem Integration (Cross-Wave)

**Goal:** Inform FormicOS's positioning in the NVIDIA agent ecosystem and cloud deployment options.

Research:

1. **NVIDIA NeMo Agent Toolkit current state (2025-2026).** Search project knowledge first for NemoClaw and NeuroStack research. What is the current state of NeMo Agent Toolkit (formerly AgentIQ)? What changed at GTC 2026? How do open-source frameworks integrate with it? What's the YAML workflow configuration format? Can FormicOS be published as a NeMo Agent Toolkit plugin?

2. **Container orchestration for AI agent workloads.** Beyond Docker Compose: what are the patterns for deploying multi-agent AI systems on Kubernetes? GPU scheduling for local LLM inference? Node affinity for Qdrant? Horizontal scaling of agent workloads? How do LangServe, CrewAI Enterprise, and AutoGen Studio deploy?

3. **Local-first AI deployment with optional cloud escalation.** FormicOS is local-first but may escalate to cloud LLMs (Anthropic, Google, OpenAI) when local models are insufficient. What are the deployment patterns for hybrid local/cloud AI systems? How do you handle API key management in Docker? Credential injection without baking secrets into images? Cost monitoring for cloud API usage from containers?

4. **RTX 5090 / consumer GPU deployment for local LLM inference.** Search project knowledge for RTX 5090 deployment research. What are the current options for running 30B+ parameter models on a single RTX 5090 (32GB VRAM)? SGLang, vLLM, llama.cpp, ExLlamav2 current performance? What quantization levels (AWQ, GPTQ, GGUF) provide the best quality/speed tradeoff for agent workloads (tool calling, structured output)?

5. **AGPLv3 compliance in containerized deployments.** FormicOS is AGPLv3. What are the compliance implications for Docker images, container registries, and SaaS deployment? Does running FormicOS in a Docker container behind an API constitute "conveying" under AGPLv3? How do Grafana and other AGPLv3 projects handle Docker distribution? What about container images that bundle AGPLv3 code with permissively-licensed dependencies?

---

## Output format

Produce a single synthesis document with these sections:

1. **Executive Summary** (1 page): The 5 most important findings that should influence Wave 41-44 decisions.

2. **Docker and Deployment Findings** (Sections 1 + 3): Concrete recommendations for container architecture, security hardening, cold-start optimization, and production readiness.

3. **Static Analysis Findings** (Section 2): What's achievable with lightweight analysis, what requires heavier tooling, and what granularity of structural context actually helps AI agents.

4. **Measurement and Publication Findings** (Section 4): Experimental design recommendations, statistical methodology, and demo/presentation best practices.

5. **Ecosystem Positioning** (Section 5): Where FormicOS fits in the NVIDIA/cloud landscape and what deployment patterns matter.

6. **Open Questions**: Anything the research couldn't resolve that the engineering team should investigate directly.

## Research principles

- Search project knowledge FIRST for every topic. It contains extensive prior research that should be the foundation.
- Use web search to fill gaps and find developments after the project knowledge was written.
- Cite sources. Distinguish between project-knowledge findings and web-search findings.
- Be honest about what you couldn't find. "No published results exist for X" is a valid and useful finding.
- Prefer concrete data (container sizes, startup times, benchmark scores, cost figures) over general commentary.
- When findings conflict, present both sides with evidence rather than picking a winner.
- Do not fabricate benchmark numbers, framework comparisons, or citations. If you can't verify a claim, say so.
- Pay special attention to what Aider, Devin, OpenHands, SWE-Agent, and Cursor do for code execution environments -- they are the closest comparable systems.
