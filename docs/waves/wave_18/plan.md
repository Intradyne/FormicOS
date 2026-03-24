# Wave 18 Plan — The Queen Gets Eyes and Hands

**Wave:** 18 — "Eyes and Hands"
**Theme:** The Queen gains read tools, safe config proposals, Blackwell-native inference, and 131k context.
**Contract changes:** 0 events. Event union stays at 36. Ports frozen.
**Estimated LOC delta:** ~280 Python, ~60 TypeScript, ~80 config/scripts

---

## Wave 18 Is a Queen Usefulness + Runtime Completion Wave

Wave 17 made telemetry truthful, landed the config validator, and tuned llama.cpp flags. Wave 18 makes the Queen actually useful to talk to and closes the local runtime gap.

The Queen currently has 3 tools: `spawn_colony`, `get_status`, `kill_colony`. She cannot see templates, inspect completed colonies, read the skill bank, browse files, or propose config changes. The operator gets more value clicking through the UI than chatting with the Queen. That's the bottleneck this wave fixes.

Simultaneously, the local runtime is leaving 8× context on the table. The same hardware runs 131k context on anyloom with the Blackwell image. FormicOS still defaults to the generic CUDA image, auto-sizing down to 16k. That gap closes here.

---

## Tracks

Three parallel tracks with one reread dependency on `queen_runtime.py`.

### Track A — Queen Read/Propose Tools (ADR-030)

**Goal:** Give the Queen 6 new tools (total: 9). All tools either read existing projections or produce text-first proposals. No live mutation. No new events.

**A1. Template tools.**
The Queen needs to see available templates before proposing teams. Two tools: `list_templates` returns summaries (id, name, description, castes, tags, use_count) for all loaded templates. `inspect_template` returns full detail for a single template by ID, including strategy, budget, max_rounds, and the complete caste composition.

These call the existing `template_manager.py` functions (`load_templates`, direct YAML read). No new persistence.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tools to `_queen_tools()` and handlers to `_execute_tool()`

**A2. Colony inspection tool.**
`inspect_colony` returns: status, display_name, quality_score, skills_extracted, round_number, max_rounds, cost, budget_limit, castes, models_used, strategy, and the last round's agent outputs (truncated to 500 chars each). Reads from `self._runtime.projections`.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler

**A3. Skill bank tool.**
`list_skills` returns the top-N skills from the bank by confidence, with text preview, confidence (alpha/beta), source colony, and freshness. Reads from `self._runtime.vector_port` using the existing `get_skill_bank_detail()` function in `view_state.py`.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler

**A4. Workspace file browser tool.**
`read_workspace_files` lists files in the workspace data directory (the colony output area). Returns filenames and sizes. Does NOT read file contents — that's a future tool. This gives the Queen awareness of what colonies have produced.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler

**A5. Config proposal tool (ADR-030).**
`suggest_config_change` takes a param path and proposed value. Runs through two gates:
1. `config_validator.py` — rejects structurally unsafe payloads (forbidden strings, depth, NaN/Inf, unknown paths)
2. `experimentable_params.yaml` — rejects out-of-Queen-scope but safe paths

If both gates pass, the tool formats a human-readable diff and returns it as text. The Queen presents this to the operator. The operator says yes or no. The tool does NOT apply the change.

This uses the existing `ApprovalRequested` event path if the operator wants formal approval tracking, or the Queen can simply present the diff in chat text. Wave 18 uses the simpler text-first approach: the Queen says "I propose changing X from Y to Z because [reason]. Say 'approve' to apply." The actual mutation path wires in a later wave.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler
- No changes to `config_validator.py` (already shipped in Wave 17)
- No changes to `experimentable_params.yaml` (already shipped in Wave 17)

**A6. Iteration limit bump.**
Raise `_MAX_TOOL_ITERATIONS` from 3 to 5. With 9 tools, the Queen needs room for multi-step interactions (e.g., list_templates → inspect_template → spawn_colony).

Files touched:
- `src/formicos/surface/queen_runtime.py` — change constant

---

### Track B — Queen Response Quality + Model Fleet

**Goal:** The Queen's system prompt leverages her new tools. Colony result follow-ups happen automatically. Opus joins the fleet.

**B1. System prompt rewrite.**
Rewrite the Queen's system prompt in `caste_recipes.yaml` to:
- Reference available tools by name with usage guidance
- Instruct the Queen to call `list_templates` before proposing teams when the task matches a known template category
- Instruct the Queen to call `inspect_colony` when asked about colony results
- Instruct the Queen to call `list_skills` when context about system knowledge is relevant
- Keep the existing structured response format (Task / Team / Why / Next)
- Maintain the "act, don't narrate" discipline

The prompt stays under 800 tokens. Additional context window goes to workspace docs and skills, not bloated caste prose.

Files touched:
- `config/caste_recipes.yaml` — update queen system_prompt

**B2. Colony completion follow-up.**
When a colony completes, if the colony was spawned by the Queen in the current thread AND the thread has been active in the last 30 minutes, schedule a Queen follow-up. The Queen calls `inspect_colony`, then emits a concise one-paragraph summary: what happened, quality score, skills extracted, and any notable issues.

This mirrors the existing `name_colony` scheduling pattern in `colony_manager.py`: after `ColonyCompleted` is emitted, schedule an async task that calls `queen_agent.follow_up_colony(colony_id, workspace_id, thread_id)`.

Bounded: one summary per colony, max 200 tokens, no chatter.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add `follow_up_colony()` method
- `src/formicos/surface/colony_manager.py` — schedule follow-up after colony completion (same pattern as `name_colony`)

**B3. Queen max_tokens alignment.**
`_queen_max_tokens()` currently reads from the caste recipe's `max_tokens` field (4096). With 131k context available, the Queen should be able to produce longer responses when needed. Align `_queen_max_tokens()` to also consider the model's `max_output_tokens` from the registry, taking the minimum of (caste max_tokens, model max_output_tokens). This prevents the Queen from being artificially capped below the model's capability.

Files touched:
- `src/formicos/surface/queen_runtime.py` — update `_queen_max_tokens()`

**B4. Add Opus 4.6 to model fleet.**
Add `anthropic/claude-opus-4.6` to the model registry in `formicos.yaml` with correct pricing ($15/$75 per 1M tokens), 200k context, tool support, vision support. Add a routing table entry: `queen: "anthropic/claude-opus-4.6"` in the `goal` phase as the heavy-tier option.

This is not the default for anything. It's the "operator explicitly wants maximum reasoning capability" option. Requires `ANTHROPIC_API_KEY` (same as Sonnet/Haiku).

Files touched:
- `config/formicos.yaml` — add registry entry and routing table entry

---

### Track C — Blackwell Image + High-Context Completion (ADR-031)

**Goal:** Port the Blackwell build, default to 131k context, scale assembly budgets.

**C1. Port Blackwell build script.**
Copy and adapt `scripts/build_llm_image.sh` from anyloom. The script clones llama.cpp, builds a Docker image with CUDA 12.8 and native sm_120 (Blackwell) kernels. The image tag is `local/llama.cpp:server-cuda-blackwell`.

The anyloom build script is proven stable. The only adaptation needed is paths and any FormicOS-specific Docker context considerations (there are none — llama.cpp builds independently).

Files touched:
- `scripts/build_llm_image.sh` — new file, adapted from anyloom

**C2. Flip image default.**
Change `LLM_IMAGE` default in `docker-compose.yml` from `ghcr.io/ggml-org/llama.cpp:server-cuda` to `local/llama.cpp:server-cuda-blackwell`. The env var override is retained — operators who haven't built the image can still set `LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda` in `.env`.

Also apply the same image default to the embed sidecar. The anyloom compose uses the Blackwell image for both LLM and embedding.

Files touched:
- `docker-compose.yml` — change `LLM_IMAGE` default for both services

**C3. Bump context to 131k.**
Change `LLM_CONTEXT_SIZE` default from 32768 to 131072 in `docker-compose.yml`. Update `context_window` for `llama-cpp/gpt-4` in `formicos.yaml` to match.

This is the same configuration running in production on anyloom on the same RTX 5090 with the same model. `--fit on` remains the OOM safety net — if VRAM is insufficient, it auto-sizes down.

Files touched:
- `docker-compose.yml` — change `LLM_CONTEXT_SIZE` default
- `config/formicos.yaml` — update `context_window` for `llama-cpp/gpt-4`

**C4. Scale context assembly budgets.**
`context.total_budget_tokens` is currently 8000 (set when context was 8k). At 131k effective context, this wastes 94% of the window. Scale to `min(effective_ctx × 0.4, 65536)` = ~52k at 131k context.

Update tier budgets proportionally:

| Tier | Old (8k ctx) | New (131k ctx) |
|------|-------------|----------------|
| `total_budget_tokens` | 8,000 | 52,000 |
| `goal` | 1,000 | 4,000 |
| `routed_outputs` | 3,000 | 20,000 |
| `max_per_source` | 1,000 | 6,000 |
| `merge_summaries` | 1,000 | 6,000 |
| `prev_round_summary` | 1,000 | 6,000 |
| `skill_bank` | 1,600 | 10,000 |
| `compaction_threshold` | 800 | 4,000 |

Include a comment in `formicos.yaml` with the scaling formula so future context changes don't leave budgets stale.

Files touched:
- `config/formicos.yaml` — update `context` section

**C5. Configured vs. effective context in UI.**
`view_state.py` already derives runtime context from `/props` (`_derive_context_window()`). The frontend should display both numbers when they differ: "131k configured / 65k effective" with a note that `--fit on` auto-sizes to available VRAM.

Files touched:
- `frontend/src/components/model-registry.ts` — render configured vs. effective when they differ

**C6. Documentation updates.**
Update `.env.example` with:
- `LLM_IMAGE` default and the instruction to run `bash scripts/build_llm_image.sh`
- `LLM_CONTEXT_SIZE` default of 131072
- Note that the generic CUDA image falls back to PTX JIT (~10× slower on Blackwell GPUs)
- Note that `EMBED_GPU_LAYERS=0` frees ~700MB VRAM if needed

Update `docs/LOCAL_FIRST_QUICKSTART.md` with the Blackwell build step.

Files touched:
- `.env.example` — update defaults and docs
- `docs/LOCAL_FIRST_QUICKSTART.md` — add Blackwell build step

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|-----------------|--------------|
| **Coder 1** | A (Queen Tools) | `queen_runtime.py` | None — starts immediately |
| **Coder 2** | B (Queen Quality + Fleet) | `caste_recipes.yaml`, `colony_manager.py`, `formicos.yaml` | Rereads `queen_runtime.py` after Coder 1 lands A1-A6 |
| **Coder 3** | C (Blackwell + Context) | `docker-compose.yml`, `formicos.yaml`, build script | None — starts immediately |

### Serialization Rules

- **Coder 1 lands A1-A6 first** on `queen_runtime.py` (new tool definitions + handlers)
- **Coder 2 rereads** `queen_runtime.py` before doing B2 (colony follow-up wiring) and B3 (max_tokens alignment)
- **Coder 3 is fully independent** — no file overlap with A or B

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `queen_runtime.py` | 1 + 2 | Coder 1 first (tools), Coder 2 rereads before B2/B3 |
| `formicos.yaml` | 2 + 3 | Coder 2 adds Opus entry. Coder 3 updates context section. Non-overlapping YAML sections. |
| `colony_manager.py` | 2 only | No overlap |
| `docker-compose.yml` | 3 only | No overlap |
| `caste_recipes.yaml` | 2 only | No overlap |

---

## Acceptance Criteria

Wave 18 is complete when:

1. **Queen has 9 tools.** `spawn_colony`, `get_status`, `kill_colony`, `list_templates`, `inspect_template`, `inspect_colony`, `list_skills`, `read_workspace_files`, `suggest_config_change` — all functional.
2. **suggest_config_change validates through both gates.** Config validator rejects forbidden/malformed. Experimentable params rejects out-of-scope. Valid proposals format as text diffs.
3. **Queen proactively summarizes colony completions** in active threads.
4. **Opus 4.6 selectable** in model registry and routing table.
5. **Blackwell build script works.** `bash scripts/build_llm_image.sh` produces `local/llama.cpp:server-cuda-blackwell`.
6. **131k context is the default.** `docker-compose.yml` defaults to Blackwell image + 131k ctx. Context assembly budgets scaled accordingly.
7. **Configured vs. effective context visible** in model registry UI.
8. **All CI gates green.** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`

### Smoke Traces

1. **Queen template flow:** Ask "spin up a code review" → Queen calls `list_templates` → finds code-review template → proposes team from template → spawns colony
2. **Queen inspection flow:** After colony completes → Queen auto-follow-up with `inspect_colony` → summary appears in chat
3. **Config proposal flow:** Ask Queen to raise coder temperature → Queen calls `suggest_config_change` → both gates pass → diff displayed → operator sees proposal text
4. **Config rejection flow:** Ask Queen to change API key → `suggest_config_change` → config_validator rejects (forbidden prefix) → Queen explains it can't modify security config
5. **Blackwell context trace:** Stack starts with Blackwell image → `/props` returns `n_ctx >= 65536` → model-registry shows configured vs. effective
6. **Opus routing trace:** Set `ANTHROPIC_API_KEY` → Opus appears in registry → route Queen goal phase to Opus → verify LLM call uses correct model

---

## Not In Wave 18

| Item | Reason | When |
|------|--------|------|
| CONFIG_UPDATE as live mutation | Proposal-only is safer first step; operator needs to trust the proposal format | Wave 19 |
| Multi-colony coordination (REDIRECT, priority) | Queen needs basics before power tools | Wave 19+ |
| VRAM monitoring via nvidia-smi | UI is truthful (null). Not blocking. | Wave 19 |
| Hypothesis tracker | Still stretch from Wave 17. Not blocking. | Wave 19 |
| Self-evolution / experimentation engine | System needs a capable Queen before it self-improves | Post-alpha |
| AG-UI / A2A adapter implementation | Interface-only is sufficient | Post-alpha |
| Sandbox adapter implementation | Config shipped in Wave 17. Adapter deferred. | Wave 19+ |
| Event union expansion | No new events needed for Queen tool surface | — |
| Context scaling beyond 131k | 131k is the validated ceiling on RTX 5090 with current model | — |
