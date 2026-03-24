# ADR-014: Gemini Provider + Defensive Structured Output

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-012 (Compute Router), Wave 9 (Routing Table)

## Context

FormicOS has two LLM adapters behind the `LLMPort` protocol: `llm_anthropic.py` (Anthropic Messages API) and `llm_openai_compatible.py` (llama.cpp / Ollama via OpenAI-compatible endpoint). The compute router (ADR-012, Wave 9) maps `(caste, phase) → model` via a YAML routing table. The `formicos.yaml` routing table has commented entries for Gemini — the slot exists but no adapter serves it.

Two problems motivate this ADR:

1. **Cost.** Claude Sonnet 4.6 at $3/$15 per M tokens is the only cloud option. Gemini 2.5 Flash at $0.30/$2.50 is 7× cheaper and adequate for structured extraction, summarization, and search tasks. Researcher and Archivist castes don't need Claude-tier reasoning.

2. **Tool-call reliability.** All three providers (including the future Gemini adapter) fail at structured output in different ways. Qwen3-30B hallucinates tool names and wraps JSON in `<think>` tags. Claude occasionally refuses tools. Gemini returns `RECITATION` blocks and sometimes stringifies `args`. Each adapter currently parses tool calls independently with no shared error recovery. A single defensive pipeline would harden all three.

## Decision

### Part A: Gemini Adapter

Add `adapters/llm_gemini.py` implementing `LLMPort` via raw `httpx.AsyncClient`. No Google SDK.

**Wire format differences encoded in the adapter:**

| Concept | OpenAI (llama-cpp) | Anthropic | Gemini |
|---------|-------------------|-----------|--------|
| Assistant role | `"assistant"` | `"assistant"` | `"model"` |
| Tool call args | JSON string (must parse) | JSON object | JSON object |
| Tool-call finish reason | `"tool_calls"` | `"tool_use"` | `"STOP"` (same as text!) |
| System prompt | In messages array | Top-level `system` field | Top-level `systemInstruction` |
| Tool result feed-back | `role: "tool"` | `role: "user"` + `tool_result` block | `role: "user"` + `functionResponse` part |

**Critical Gemini quirks:**
- `finishReason: "STOP"` for both text and tool calls. Detect tool calls by checking for `functionCall` in response parts.
- `thoughtSignature` bytes on `functionCall` parts when thinking mode is active. These MUST be preserved and sent back in subsequent turns or context breaks silently.
- `RECITATION` and `SAFETY` blocks cannot be disabled. Surface as `finish_reason: "blocked"` and trigger fallback chain.

**Adapter registration:** `gemini/` prefix in adapter factory. `gemini/gemini-2.5-flash` routes to `GeminiAdapter` with model string `gemini-2.5-flash`.

**Auth:** `x-goog-api-key` header from `GEMINI_API_KEY` env var. Same pattern as `ANTHROPIC_API_KEY`.

### Part B: Defensive Structured Output Pipeline

Add `adapters/parse_defensive.py` — a shared 3-stage tool-call parser used by ALL three adapters:

- **Stage 1:** `json.loads()` — fast path for clean JSON
- **Stage 2:** `json_repair.loads()` — fixes trailing commas, missing quotes, truncation. Safe on every response (tries `json.loads()` internally first).
- **Stage 3:** Regex extraction — strip `<think>` tags, find JSON in markdown fences, find bare JSON objects

Additional normalization:
- Fuzzy-match hallucinated tool names against known tools via `difflib.get_close_matches(cutoff=0.6)`
- Handle `args` as JSON string (parse if string, pass through if object)
- Log which stage succeeded via structlog field `parse_stage`

### Part C: Routing Table Update

Uncomment Gemini entries in `formicos.yaml`:
- `researcher` execute phase → `gemini/gemini-2.5-flash` (1M context, cheap for search/extraction)
- `archivist` execute phase → `gemini/gemini-2.5-flash` (cheap for summarization)
- Add `gemini-flash` and `gemini-flash-lite` to model registry with cost rates

### Part D: Fallback Chain

When a provider returns `finish_reason: "blocked"`, the caller retries with the next model in the fallback chain:
```
gemini/* → llama-cpp/gpt-4 → anthropic/claude-sonnet-4.6
```

This is implemented in the runner's tool loop (< 20 lines). The router provides the fallback address from the routing config.

## Consequences

- **New dependency:** `json-repair>=0.30` added to `pyproject.toml`
- **New adapter file:** `adapters/llm_gemini.py` (~300 LOC)
- **New utility file:** `adapters/parse_defensive.py` (~150 LOC)
- **Modified adapters:** `llm_openai_compatible.py` and `llm_anthropic.py` adopt `parse_tool_calls_defensive()` for tool-call parsing
- **Modified surface:** `runtime.py` adapter factory gains `gemini/` prefix branch
- **No contract changes:** LLMPort interface is unchanged
- **No engine changes:** Engine calls `llm_port.complete()`, never knows which provider
- **Cost impact:** Researcher + Archivist routing to Gemini Flash saves ~80% on those castes vs. Claude Sonnet
- **Rollback:** Remove Gemini entries from routing table → system falls back to cascade default (local or Claude)
