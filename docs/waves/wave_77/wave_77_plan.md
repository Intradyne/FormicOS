# Wave 77 Plan: Cloud-First Default + Filesystem Working Memory

**Theme:** Lower the barrier to first run (no GPU, 3 containers) and implement
the AI Filesystem pattern (Pan et al. 2026) — state/artifact separation and
amnesiac context forking for colony retries.
**Teams:** 2 tracks, independent dispatch. Track A is infrastructure-only
(immediate). Track B requires ADR-052 (dispatches as Wave 77.5 or 78).
**Estimated total change:** Track A ~150 lines config/docs/scripts, Track B
~400 lines production code + ~200 lines tests.
**Research basis:** 6 FormicOS knowledge base entries + Pan et al. "Natural-Language
Agent Harnesses" (arXiv:2603.25723, March 2026).

---

## Knowledge base grounding

Findings from 6 knowledge searches inform this plan:

| Entry | Key insight | Influences |
|-------|-------------|------------|
| *Memory Architectures for Agent Systems: Short-Term, Long-Term, and Tiered* (1.0) | Three-tier pattern (working / episodic / semantic) is the established architecture. FormicOS already has episodic (events) and semantic (knowledge bank). Missing: explicit working memory tier. | Track B: working memory is the gap |
| *Scratchpads and Working Memory Patterns for Agent Loops* (1.0) | File-backed scratchpads outperform in-context-only memory for multi-step reasoning. Key: structured format, automatic summarization on overflow, read-before-write discipline. | Track B: file-backed design, structured format |
| *Context Window Budget Allocation for Production Agent Systems* (1.0) | Budget allocation should be proportional and capped. Working memory slot should not exceed 10% of context budget. | Track B: 10th budget slot at 5% of total |
| *Local-First vs Cloud-Only: Decision Framework* (0.667) | Cloud-only deployment should be the simplest path; local GPU is an optimization. First-run experience should not require hardware setup. | Track A: cloud-first default |
| *Confidence-Based Model Routing* (0.625) | Cheapest capable model per request. Cloud defaults should use cost-effective models, not frontier. | Track A: Sonnet for queen, Haiku for workers |
| *Context Compression Techniques* (0.667) | Summarization is the right compaction strategy for working memory overflow. | Track B: summarize-on-overflow for working files |

---

## Track A: Cloud-First Default Stack

**Goal:** `cp .env.example .env && docker compose up -d` starts 3 containers
(FormicOS + Qdrant + Docker proxy) with cloud API inference. No GPU, no model
downloads. One local image build (the FormicOS app itself) is required.

**Approach:** Use Docker Compose profiles to make GPU containers opt-in.
Change `formicos.yaml` defaults to cloud models via env vars. Update docs
and `.env.example` to lead with cloud path. Fix two bootstrap blockers:
the machine-specific benchmark mount and the embedding dimension contract.

### A0: Bootstrap blockers

Two things in the live `docker-compose.yml` break the cloud-first promise
on fresh machines:

1. **`build: .` (line 115):** The `formicos` service requires a local image
   build. This is acceptable — the app image is what we ship. But the plan
   must not claim "no image builds." First-run is:
   `docker compose build && docker compose up -d`, or we publish a pre-built
   image to a registry. For now, we accept the build step and document it.

2. **Machine-specific benchmark mount (line 122):**
   `C:/Users/User/polyglot-benchmark:/benchmark:ro` — this hard path breaks
   on any machine that isn't the operator's. Fix: move to a profile or
   make it conditional via env var:
   ```yaml
   volumes:
     - formicos-data:/data
     - ${BENCHMARK_DIR:-/dev/null}:/benchmark:ro
   ```
   Or simpler: remove the mount from the default compose and add it to a
   `docker-compose.dev.yml` overlay. The benchmark is development tooling,
   not runtime infrastructure.

**Files:**
| File | Change |
|------|--------|
| `docker-compose.yml` | Remove or conditionalize benchmark mount; clarify that `build: .` is expected |

### A1: Docker Compose profiles

**Current state:**
- `docker-compose.yml` has `llm` and `formicos-embed` as required services
- `formicos` service `depends_on` all 4 peers (llm, qdrant, embed, docker-proxy)
- `LLM_HOST=http://llm:8080` hardcoded in formicos environment

**Target state:** Use Docker Compose
[profiles](https://docs.docker.com/compose/how-tos/profiles/) to make GPU
containers opt-in. Services tagged with `profiles: [local-gpu]` are **not
started by default** — they only start when `COMPOSE_PROFILES=local-gpu`
is set in `.env` or `--profile local-gpu` is passed on the CLI.

Changes to `docker-compose.yml`:
- Add `profiles: [local-gpu]` to `llm` and `formicos-embed` services
- Move `LLM_HOST` and `EMBED_URL` from hardcoded environment to
  `${LLM_HOST:-}` and `${EMBED_URL:-}` (empty when unset = adapter uses
  formicos.yaml defaults which point to cloud)
- Change `depends_on` for formicos: remove `llm` and `formicos-embed`
  (profile-gated services cannot be hard dependencies). The adapter
  factory already handles unreachable endpoints gracefully — errors
  surface at first LLM call, then fallback chain activates.

**Usage (controlled entirely by `.env`):**
```bash
# Cloud-first (default .env.example — no COMPOSE_PROFILES set)
docker compose up -d                  # 3 containers, needs API keys

# Local GPU (user's .env has COMPOSE_PROFILES=local-gpu + model overrides)
docker compose up -d                  # 5 containers, same command
```

No overlay files needed. One `docker-compose.yml`. One `.env`.

**Files:**
| File | Change |
|------|--------|
| `docker-compose.yml` | Add `profiles: [local-gpu]` to llm + embed; env-var-ize LLM_HOST/EMBED_URL; remove hard depends_on for profiled services |

### A2: formicos.yaml env-var-driven defaults

**Current state:** All caste defaults are hardcoded `llama-cpp/gpt-4` (line 31-35).

**Target state:** Caste defaults use `${VAR:default}` interpolation (already
supported by `_interpolate_recursive` in `core/settings.py`). The YAML
defaults are cloud-first; local-GPU users override via `.env`.

Informed by *Confidence-Based Model Routing*: use cheapest capable model.

```yaml
defaults:
  queen: "${QUEEN_MODEL:anthropic/claude-sonnet-4-6}"
  coder: "${CODER_MODEL:anthropic/claude-sonnet-4-6}"
  reviewer: "${REVIEWER_MODEL:anthropic/claude-haiku-4-5}"
  researcher: "${RESEARCHER_MODEL:anthropic/claude-haiku-4-5}"
  archivist: "${ARCHIVIST_MODEL:anthropic/claude-haiku-4-5}"
```

Local-GPU `.env` overrides:
```bash
QUEEN_MODEL=llama-cpp/gpt-4
CODER_MODEL=llama-cpp/gpt-4
REVIEWER_MODEL=llama-cpp/gpt-4
RESEARCHER_MODEL=llama-cpp/gpt-4
ARCHIVIST_MODEL=llama-cpp/gpt-4
```

This means:
- `formicos.yaml` ships cloud-first out of the box (no edits needed)
- Personal `.env` switches the entire stack to local GPU with 5 lines
- The workspace model cascade still overrides per-workspace/thread
- No code changes — `_interpolate_recursive` already handles this

**Routing table** (`model_routing` block, lines 574-584): Also convert to
env-var-driven with cloud defaults. Local-GPU users override via `.env`.

**Embedding endpoint:** Already uses `${EMBED_URL:http://localhost:8200}`.
For cloud-first default, change the fallback to empty or localhost (triggers
sentence-transformers fallback). Local-GPU `.env` sets
`EMBED_URL=http://formicos-embed:8200`.

**Files:**
| File | Change |
|------|--------|
| `config/formicos.yaml` | Wrap caste defaults + routing table in `${VAR:default}` patterns |

### A3: .env.example and docs

**Current state:** `.env.example` leads with local LLM image build.
Cloud keys are "optional" comments.

**Target state:** Two sections with clear separation. Cloud API keys first
(active, with placeholders). Local GPU section second (all commented, ready
to uncomment). Personal `.env` inherits whichever section you activate.

`.env.example` target layout:
```bash
# FormicOS environment configuration
# Copy to .env and set your API key. That's it.
#
# Cloud-first by default: 3 containers, no GPU needed.
# For local GPU: uncomment the "Local GPU" section below,
# then run: bash scripts/setup-local-gpu.sh

# --- Cloud API keys (set at least one) ---
ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=AI...
# OPENAI_API_KEY=sk-...

# --- Local GPU override (uncomment entire block) ---
# COMPOSE_PROFILES=local-gpu
# QUEEN_MODEL=llama-cpp/gpt-4
# CODER_MODEL=llama-cpp/gpt-4
# REVIEWER_MODEL=llama-cpp/gpt-4
# RESEARCHER_MODEL=llama-cpp/gpt-4
# ARCHIVIST_MODEL=llama-cpp/gpt-4
# LLM_HOST=http://llm:8080
# EMBED_URL=http://formicos-embed:8200
#
# Local LLM tuning:
# LLM_IMAGE=local/llama.cpp:server-cuda-blackwell
# LLM_MODEL_FILE=Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
# LLM_CONTEXT_SIZE=80000
# LLM_SLOTS=2
# LLM_SLOT_PROMPT_SIMILARITY=0.5
# LLM_CACHE_RAM=1024
# EMBED_GPU_LAYERS=99
# CUDA_DEVICE=0
```

### A3.1: Local GPU setup script

`scripts/setup-local-gpu.sh` — one command to prepare the local GPU stack:

```bash
#!/usr/bin/env bash
set -euo pipefail
# Download models + build Blackwell image + enable local-gpu profile in .env

echo "==> Downloading models..."
mkdir -p .models && cd .models
huggingface-cli download Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf --local-dir .
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .
cd ..

echo "==> Building Blackwell llama.cpp image..."
bash scripts/build_llm_image.sh

echo "==> Enabling local-gpu profile in .env..."
# Uncomment the local GPU block if present, or append
if grep -q "# COMPOSE_PROFILES=local-gpu" .env 2>/dev/null; then
  sed -i 's/# COMPOSE_PROFILES=local-gpu/COMPOSE_PROFILES=local-gpu/' .env
  sed -i 's/# QUEEN_MODEL=llama-cpp/QUEEN_MODEL=llama-cpp/' .env
  sed -i 's/# CODER_MODEL=llama-cpp/CODER_MODEL=llama-cpp/' .env
  sed -i 's/# REVIEWER_MODEL=llama-cpp/REVIEWER_MODEL=llama-cpp/' .env
  sed -i 's/# RESEARCHER_MODEL=llama-cpp/RESEARCHER_MODEL=llama-cpp/' .env
  sed -i 's/# ARCHIVIST_MODEL=llama-cpp/ARCHIVIST_MODEL=llama-cpp/' .env
  sed -i 's/# LLM_HOST=http:\/\/llm:8080/LLM_HOST=http:\/\/llm:8080/' .env
  sed -i 's/# EMBED_URL=http:\/\/formicos-embed:8200/EMBED_URL=http:\/\/formicos-embed:8200/' .env
fi

echo "==> Done. Run: docker compose up -d"
```

**A3 + A3.1 files:**
| File | Change |
|------|--------|
| `.env.example` | Cloud keys + model vars active at top; local GPU section commented below |
| `scripts/setup-local-gpu.sh` | **NEW** — downloads models, builds image, enables local-gpu in .env. **Linux/WSL/Git Bash only** (matches `build_llm_image.sh`). |
| `docs/DEPLOYMENT.md` | Restructure Quick Start: cloud path first, local GPU as "Advanced" section |
| `docs/LOCAL_FIRST_QUICKSTART.md` | Add cloud-first quick start at top; rename existing content as "Local GPU Quick Start" |
| `README.md` | Simplify Quick Start to `cp .env.example .env` + add API key + `docker compose build && docker compose up -d` |

### A4: Embedding fallback (BLOCKING for Track A)

**Current state:** `formicos.yaml` embedding model is `qwen3-embedding-0.6b`.
`_build_embed_fn()` in `app.py:124-129` explicitly **skips** models starting
with `qwen3-embedding` (returns `None`), because it assumes those run via the
sidecar HTTP client, not sentence-transformers. When the sidecar is absent
AND the config says `qwen3-embedding-0.6b`, BOTH paths return None and
embedding breaks.

**Fix:** Add an `EMBED_MODEL` env var to `formicos.yaml`:
```yaml
embedding:
  model: "${EMBED_MODEL:all-MiniLM-L6-v2}"
  endpoint: "${EMBED_URL:}"
```
- Cloud-first default (`EMBED_URL` unset, `EMBED_MODEL` unset): endpoint is
  empty string → sidecar client skipped → `_build_embed_fn("all-MiniLM-L6-v2")`
  → sentence-transformers activates with a small model (~80MB auto-download).
- Local-GPU `.env`: `EMBED_URL=http://formicos-embed:8200` and
  `EMBED_MODEL=qwen3-embedding-0.6b` → sidecar client activates, sentence-
  transformers skipped for qwen3-embedding prefix.

**Dimension contract:** The live config is `dimensions: 1024`
(`formicos.yaml:554`), and `create_app()` threads `settings.embedding.dimensions`
into Qdrant collection setup (`app.py:238`). MiniLM produces 384-dim vectors.
If the dimension config doesn't change with the model, Qdrant rejects every
upsert.

Fix: make dimensions env-var-driven too:
```yaml
embedding:
  model: "${EMBED_MODEL:all-MiniLM-L6-v2}"
  endpoint: "${EMBED_URL:}"
  dimensions: ${EMBED_DIMENSIONS:384}
```
Local-GPU `.env` sets `EMBED_DIMENSIONS=1024` alongside `EMBED_MODEL` and
`EMBED_URL`. The `setup-local-gpu.sh` script uncomments the full block.

**Implication:** Cloud-first users get 384-dim MiniLM embeddings (lower
quality, ~80MB auto-download). Local-GPU users get 1024-dim Qwen3 via
sidecar. The dimension mismatch means **you cannot switch between cloud and
local embedding on an existing Qdrant collection without re-indexing.** This
is acceptable for the onboarding path — users commit to a stack at collection
creation time. Document this constraint.

**Files:**
| File | Change |
|------|--------|
| `config/formicos.yaml` | Wrap embedding model + endpoint + dimensions in `${VAR:default}` |
| `.env.example` | Add `EMBED_MODEL`, `EMBED_URL`, `EMBED_DIMENSIONS` to local-GPU section |
| `surface/app.py` | Handle empty `embed_endpoint` gracefully (skip sidecar client when empty string) |
| `docs/DEPLOYMENT.md` | Document dimension lock-in: switching embedding model requires Qdrant re-index |

### Track A validation

```bash
# 1. Cloud path (default)
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...
docker compose build && docker compose up -d
docker compose ps         # → 3 containers: formicos, qdrant, docker-proxy
curl http://localhost:8080/health   # → 200
# Verify: knowledge search works (MiniLM 384-dim embeddings)

# 2. Local GPU path (same .env, add profile + model overrides)
bash scripts/setup-local-gpu.sh     # downloads models, builds LLM image, patches .env
docker compose up -d                # rebuilds if needed
docker compose ps         # → 5 containers: + llm, embed
# NOTE: switching embedding model requires Qdrant re-index (dimension mismatch)
```

---

## Track B: AI Filesystem — State/Artifact Separation + Amnesiac Forking (requires ADR-052)

**Goal:** Implement the AI Filesystem pattern from Pan et al. (2026,
arXiv:2603.25723): externalize Queen and colony reasoning into a structured
file tree with explicit separation between intermediate runtime state and
final artifacts. Add amnesiac context forking for failed colonies.

**Design rationale:** Three converging sources:

- **Knowledge base** (*Memory Architectures for Agent Systems*): Production
  agents need three memory tiers — working, episodic, semantic. FormicOS has
  episodic (events) and semantic (knowledge bank) but lacks explicit working
  memory.
- **Knowledge base** (*Scratchpads and Working Memory Patterns*): File-backed
  scratchpads outperform in-context-only memory for multi-step reasoning.
- **NLAH paper** (Pan et al. 2026): The AI Filesystem separates `STATE_ROOT`
  (intermediate scratchpads, reflections) from `artifacts/` (final
  deliverables). Only artifacts feed into retrieval. Amnesiac context forking
  on failure yields 47.2% vs 30.4% task success on OSWorld (55% relative
  improvement). 90% of operational activity successfully pushed to child
  agents with file-backed coordination.

### B1: ADR-052 — AI Filesystem + Amnesiac Forking

Must be written and approved before dispatch. Key decisions:

1. **Directory structure** — follows existing `{category}/{workspace_id}/`
   convention (matching `operations/{workspace_id}/` from operational_state.py):
   ```
   .formicos/
   ├── runtime/{workspace_id}/     # STATE_ROOT — intermediate, ephemeral
   │   ├── queen/                  # Queen reasoning scratchpad, decision logs
   │   ├── colonies/{colony_id}/   # Per-colony working files
   │   │   └── reflection.md       # Written on failure, read by retry colony
   │   └── shared/                 # Cross-colony coordination state
   └── artifacts/{workspace_id}/   # Final deliverables, stable
       ├── plans/                  # Completed plans, milestone summaries
       └── deliverables/           # Colony output products
   ```
   This follows the NLAH paper's `STATE_ROOT` vs `artifacts/` separation.
   `runtime/` is the scratchpad layer — cheap, disposable, never feeds
   into knowledge retrieval. `artifacts/` is the deliverable layer — stable,
   retrievable, eligible for knowledge extraction.

2. **Amnesiac context forking** (NLAH Recommendation 1):
   When a colony fails and the Queen retries the task:
   - `_post_colony_hooks` writes `runtime/colonies/{colony_id}/reflection.md`
     **only when `succeeded=False`**. Success path skips reflection (nothing
     to reflect on). Kill path skips reflection (no useful reflection from
     a killed colony — kill bypasses `_post_colony_hooks` via the Wave 76
     completion guard).
   - **Reflection content:** `_post_colony_hooks` has access to `colony.task`,
     `colony.failure_reason`, `colony.strategy`, `colony.castes`,
     `rounds_completed`, `quality`, and `stall_count`. It does NOT have the
     colony transcript. To get a useful "what was attempted" summary, the
     hook fetches the last round summary from `projections.colony_rounds`
     (O(1) lookup). The reflection format:
     ```
     ## Reflection: {colony_id}
     Task: {colony.task[:500]}
     Failure: {colony.failure_reason}
     Rounds completed: {rounds_completed}, Quality: {quality}
     Last round summary: {last_round_summary[:500]}
     Strategy: {colony.strategy}
     ```
   - **Retry integration:** The existing `retry_colony` Queen tool
     (`queen_tools.py:2540`) already builds a `retry_task` string with the
     failure reason inline (line 2584). The change: instead of embedding
     the full failure context in the task string, `_retry_colony` prefixes
     the task with `[retry_of:{colony_id}]` and keeps the original task
     text clean. The reflection file (written by `_post_colony_hooks` on
     failure) provides the structured failure analysis.
   - **Persistence:** The `[retry_of:...]` prefix is persisted in
     `ColonySpawned.task` — replay-safe, no event schema changes, no
     projection metadata bag needed.
   - **Context assembly:** `assemble_context()` in `engine/context.py:453`
     detects the `[retry_of:...]` prefix and reads
     `runtime/colonies/{original_id}/reflection.md`. The reflection is
     injected as an `input_source` (ADR-033 chained colony context, high
     attention position 2b). No thread context suppression needed — colony
     context assembly doesn't inject Queen thread context. Colonies already
     get fresh context per round.
   - **Token savings:** Avoids re-reading the failed attempt's full output
     (often 2000-5000 tokens of stack traces and bad code). Directly improves
     daily budget efficiency.

3. **State/Artifact boundary rule:**
   - `runtime/` files are NEVER extracted as knowledge entries. The knowledge
     extraction pipeline (`transcript.py`, hook position 4.5) must skip
     entries sourced from `runtime/` paths. This prevents the Bayesian
     knowledge system from being poisoned by intermediate hallucinations
     (NLAH paper Section 6, Recommendation 4).
   - `artifacts/` files ARE eligible for knowledge extraction via the
     existing `MemoryEntryCreated` path.

4. **Context budget:** New 10th slot `working_memory` in `queen_budget.py`
   at 5% of total (400-token fallback). Reads from `runtime/queen/` and
   `runtime/shared/`. Informed by *Context Window Budget Allocation*:
   working memory should not exceed 10% of context budget.

5. **Colony access:** Colonies do NOT write to `runtime/` during execution
   rounds (preserving the events-only invariant for round execution).
   File writes happen at two boundaries:
   - **Post-colony hooks** (`_post_colony_hooks`): Write reflection.md on
     failure, write deliverables to `artifacts/` on success.
   - **Queen tool invocation**: Queen writes to `runtime/queen/` via tools.

6. **Queen tools:** Two new Queen tools (43 → 45):
   - `write_working_note` — write/append to `runtime/queen/{filename}`
   - `promote_to_artifact` — move a runtime file to artifacts/ (marks it
     as a stable deliverable, eligible for knowledge extraction)
   Reading is handled by the `working_memory` budget slot injection — the
   Queen sees `runtime/queen/` and `runtime/shared/` content automatically.
   `list_working_files` is deferred — the budget slot injection includes a
   file manifest header. Adding more tools increases tool selection surface
   and degrades choice accuracy. Ship minimal, add if Queen demonstrably
   needs explicit read/list.

7. **No new events.** The AI Filesystem is file-backed, not event-sourced.
   This is intentional and validated by the NLAH paper: "frozen weights +
   file-backed state is the correct production architecture." Working files
   are ephemeral task state. The knowledge bank remains the durable store.
   Events record what happened (colony succeeded/failed); files record how
   the system reasoned about it.

8. **Summarize-on-overflow** (compaction):
   When a runtime file exceeds a configurable token limit (default: 2000
   tokens), compaction occurs in two stages:
   - **Immediate (on budget slot injection):** If a file exceeds the
     budget slot allocation, it is **truncated** for context injection
     (tail-biased: keep the last N tokens). The file on disk is untouched.
   - **Background (during operational sweep):** The sweep identifies
     oversized runtime files and schedules archivist-caste summarization.
     The LLM call happens asynchronously, not in the file-write path.
     The summarized file replaces the original with a
     `[summarized at {timestamp}]` marker.
   This avoids introducing LLM calls into file I/O paths. Informed by
   *Context Compression Techniques*.

### B2: Implementation (post-ADR)

| Component | Change |
|-----------|--------|
| `surface/ai_filesystem.py` | **NEW** — file I/O: `write_note()`, `read_notes_for_budget()`, `write_reflection()`, `promote_to_artifact()`, `summarize_oversized()` |
| `surface/queen_tools.py` | Add 2 tools (`write_working_note`, `promote_to_artifact`) to `tool_specs()` and `_handlers` dict. Modify `_retry_colony` to prefix task with `[retry_of:{colony_id}]` instead of embedding failure context inline. |
| `surface/queen_budget.py` | Add 10th slot `working_memory` at 5%; rebalance remaining 9 slots proportionally |
| `surface/queen_runtime.py` | Inject `runtime/queen/` + `runtime/shared/` content at budget slot (with file manifest header); truncate oversized files tail-biased |
| `surface/colony_manager.py` | In `_post_colony_hooks`: write `reflection.md` on failure only (`succeeded=False`). Fetch last round summary from projections for reflection content. In `extract_institutional_memory()` (~line 2066): skip extraction for `runtime/` paths. |
| `engine/context.py` | In `assemble_context()`: detect `[retry_of:...]` prefix in task, read reflection file, inject as `input_source` |
| `surface/colony_manager.py` | In `extract_institutional_memory()` (~line 2066): skip extraction when colony deliverables originate from `runtime/` paths |
| `surface/app.py` | In `_operational_sweep_body()` (~line 956): add step for oversized runtime file detection + archivist summarization scheduling |
| Tests | Unit tests for: file I/O helpers, reflection write (failure only, not success/kill), `[retry_of:...]` prefix parsing, amnesiac context assembly (reflection injected as input_source), budget slot injection with truncation, artifact promotion, `extract_institutional_memory()` runtime path filtering, sweep summarization scheduling |

### B3: Future work (not in this wave)

These are informed by NLAH Recommendations 2 and 3 but are too large for
Wave 77. They become candidates for Wave 78+:

- **Executable NLAHs (Recommendation 2):** Elevate operating procedures
  from passive markdown to stage-gated contracts. Add `StageGate` concept
  to operational state layer — the sweep can't proceed past a stage unless
  a specific artifact file exists. File-backed validation, no new events.

- **Orchestrator-only charter hardening (Recommendation 3):** Audit the
  Queen's 43 tools and classify each as orchestrator-appropriate or
  delegation-required. Consider removing direct-action tools like
  `draft_document` and routing them through colony delegation instead.
  The paper's 90% delegation rate validates this direction.

### Track B validation

```bash
# 1. Full CI green
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# 2. Amnesiac forking test
# - Start FormicOS, create workspace, spawn a colony that will fail
# - Verify reflection.md written at .formicos/runtime/{ws_id}/colonies/{id}/reflection.md
# - Queen retries the task via retry_colony
# - Verify retry colony task has [retry_of:{original_id}] prefix
# - Verify assemble_context() reads reflection as input_source
# - Verify retry colony does NOT re-read the full failed output

# 3. State/artifact separation test
# - Queen writes to runtime/{ws_id}/queen/scratchpad.md via write_working_note
# - Verify file appears at .formicos/runtime/{ws_id}/queen/scratchpad.md
# - Verify runtime/ files are NOT extracted by extract_institutional_memory()
# - Queen promotes a file to artifacts/ via promote_to_artifact
# - Verify promoted file IS eligible for knowledge extraction

# 4. Budget slot test
# - Verify working_memory slot is 5% of total context budget
# - Verify runtime/queen/ content injected into Queen context
```

---

## Dispatch sequence

1. **Track A dispatches immediately** — infrastructure and config changes only,
   no production Python code changes beyond verifying the embedding fallback.
   Single coder prompt.

2. **Track B: ADR-052 first** — write and get operator approval. Then dispatch
   as Wave 77.5 or Wave 78 depending on scope review.

## Pre-dispatch checklist

- [ ] All file paths verified against live codebase
- [ ] No ADR conflicts (Track A: no new events, no layer violations;
      Track B: requires ADR-052)
- [ ] Docker compose profiles tested locally (cloud path + local-gpu path)
- [ ] Cloud-first path verified end-to-end with API key
- [ ] Shared-file ownership boundaries confirmed
- [ ] Track B: reflection write site in `_post_colony_hooks` reviewed for
      race conditions with kill/completion guard (Wave 76 Track 9)

## Risk assessment

| Risk | Mitigation |
|------|-----------|
| Breaking local-GPU users | Profiles preserve exact current behavior. `setup-local-gpu.sh` makes transition one command. README/docs guide both paths. |
| Adapter factory errors on missing cloud keys | Adapters already create lazily — errors surface at first LLM call, not startup. Need clear error message pointing to API key setup. |
| Embedding fallback not working | A4 explicitly verifies this before declaring Track A done |
| Runtime files growing unbounded | Summarize-on-overflow with configurable limit |
| Colony execution writing files (invariant violation) | ADR-052 explicitly prohibits round-time writes. File writes at post-colony hooks and Queen tool boundaries only. |
| Knowledge poisoning from intermediate state | `runtime/` path exclusion in transcript extraction. Explicit state/artifact boundary. |
| Reflection.md race with colony kill | Post-colony hook runs after completion guard (Wave 76). Kill path skips reflection (no useful reflection from a killed colony). |
| Retry colony re-reads failed context | `_retry_colony` uses `[retry_of:...]` prefix instead of inlining failure context. `assemble_context` injects focused reflection (~300 tokens) as `input_source` instead of full failure dump (2000-5000 tokens). Colony assembly already excludes Queen thread context. |
| Dimension mismatch on embedding switch | Cloud-first (384-dim MiniLM) and local-GPU (1024-dim Qwen3) cannot share Qdrant collections. Documented as a one-time choice at collection creation. |
