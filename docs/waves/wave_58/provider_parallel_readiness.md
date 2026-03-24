# Provider Packet: Parallel Readiness + Ollama Cloud

## Context

Wave 58's three feature teams are about knowledge injection quality:

- specificity gate
- trajectory storage
- progressive disclosure

The multi-provider colony experiment is adjacent work, not hidden scope
inside those teams. It needs one small, explicit packet so provider truth
is settled before we spend more GPU or paid-provider budget.

Important current-repo truths:

1. Normal colony tool-calling already goes through
   `OpenAICompatibleLLMAdapter.complete()`, which is non-streaming today.
   Do not assume the first Ollama fix is "force stream=false everywhere" --
   that path is already non-streaming for colony tool calls.
2. The real readiness gaps are:
   - benchmark-confirming tool-call compatibility on the host
   - registry entries for confirmed providers
   - truthful surface treatment for an Ollama Cloud provider
3. Plain `ollama/*` is currently treated as a local provider in parts of the
   surface (`view_state.py`, `ws_handler.py`). Reusing that prefix for a cloud
   endpoint will create truth drift unless you handle it deliberately.

## Mission

Make the multi-provider experiment real and truthful:

1. Add a host-side provider benchmark script
2. Add registry entries for benchmark-confirmed cloud providers
3. Handle Ollama Cloud explicitly so it is not misrepresented as local
4. Only add an adapter safeguard if a real caller uses stream+tools together

## Recommended provider naming

Use a distinct provider prefix for Ollama Cloud:

- `ollama-cloud/qwen3-coder:480b`

Why:

- `OpenAICompatibleLLMAdapter` can already serve any non-Anthropic,
  non-Gemini provider prefix
- `ollama/*` is currently treated as local in the surface
- `ollama-cloud/*` avoids accidental local probing and keeps the experiment
  semantically honest

## Implementation

### Change 1: Host benchmark script

**File**: `scripts/provider_benchmark.py`

Create the host-side compatibility script described in the experiment plan.
Requirements:

- parallel requests via `asyncio.gather`
- OpenAI-compatible path for Ollama Cloud, OpenAI, Gemini
- Anthropic native Messages API path for Anthropic
- same tool-calling prompt for all providers
- output a compact summary table:
  - provider
  - status
  - latency
  - tool called?
  - tool args correct?

Keep this script standalone. It runs on the host, not in Docker.

### Change 2: Registry entries for confirmed providers

**File**: `config/formicos.yaml`

Add cloud-provider entries only for providers that Phase A benchmark confirms.

At minimum, wire the registry shape for:

- `ollama-cloud/qwen3-coder:480b`
- `openai/gpt-4o-mini`

Recommended Ollama Cloud entry:

```yaml
    - address: "ollama-cloud/qwen3-coder:480b"
      endpoint: "https://ollama.com"
      api_key_env: "OLLAMA_API_KEY"
      context_window: 262144
      supports_tools: true
      supports_vision: false
      cost_per_input_token: 0.0
      cost_per_output_token: 0.0
      max_output_tokens: 16384
      time_multiplier: 2.0
      tool_call_multiplier: 1.5
```

Recommended OpenAI entry:

```yaml
    - address: "openai/gpt-4o-mini"
      endpoint: "https://api.openai.com"
      api_key_env: "OPENAI_API_KEY"
      context_window: 128000
      supports_tools: true
      supports_vision: true
      cost_per_input_token: 0.00000015
      cost_per_output_token: 0.0000006
      max_output_tokens: 16384
      time_multiplier: 2.0
      tool_call_multiplier: 1.0
```

Note:

- the app already normalizes OpenAI-compatible endpoints to `/v1`
- do not add a cloud entry that failed the benchmark just because it is
  interesting on paper

### Change 3: Surface truth for cloud providers

**File**: `src/formicos/surface/view_state.py`

Update cloud-provider classification so the new provider appears in the
connected cloud endpoint list instead of vanishing into an unknown bucket.

At minimum:

- add `ollama-cloud` to `_CLOUD_PROVIDERS`

While you are in this file, also check whether existing shipped cloud
providers are missing from `_CLOUD_PROVIDERS` (for example `deepseek`,
`minimax`). If they are, fix them under the audit allowance and report it.

### Change 4: Adapter timeout parameterization

**Files**: `src/formicos/adapters/llm_openai_compatible.py`,
`src/formicos/surface/runtime.py` (LLMRouter)

The httpx client timeout is hardcoded at 120s (line 127):

```python
self._client = httpx.AsyncClient(
    base_url=base_url,
    timeout=httpx.Timeout(120.0),
)
```

This blocks two use cases: CPU-hosted archivist models (3-5 tok/s, need
~330s for extraction) and slow cloud endpoints (Ollama free tier under
load). The call silently fails at 120s with `memory_extraction.llm_failed`.

**The fix uses existing infrastructure.** Every `ModelRecord` already has
`time_multiplier: float` (default 1.0) on `core/types.py:216`. The
`LLMRouter` already has `_registry_map: dict[str, ModelRecord]` (line 193).
The algorithm:

1. In `LLMRouter.complete()`, look up the model's `time_multiplier`:
   ```python
   rec = self._registry_map.get(model)
   timeout_s = 120.0 * (rec.time_multiplier if rec else 1.0)
   ```
2. Pass `timeout_s` through to `adapter.complete()`
3. In the adapter's `complete()`, use httpx per-request timeout override:
   ```python
   resp = await self._client.post(url, json=body, timeout=httpx.Timeout(timeout_s))
   ```

This is backward-compatible: `time_multiplier: 1.0` (the default) gives
120s, identical to current behavior. A CPU model with `time_multiplier: 3.0`
gets 360s. An Ollama Cloud entry with `time_multiplier: 2.0` gets 240s.
No new config fields, no special cases, no hardcoded model-specific timeouts.

**Touch points** (~10 lines total):
- `LLMRouter.complete()` in `surface/runtime.py`: compute `timeout_s`,
  pass to adapter
- `LLMRouter._complete_with_fallback()`: same pattern for fallback path
- `OpenAICompatibleLLMAdapter.complete()`: accept `timeout_s` parameter,
  pass to `self._client.post()`
- Optionally `llm_anthropic.py` and `llm_gemini.py` for consistency
  (same pattern: accept `timeout_s`, pass to their HTTP clients)

**Do NOT change the `LLMPort` Protocol** in `core/ports.py` — that's a
contract file requiring operator approval.

**Pyright workaround**: `LLMRouter._adapters` is typed `dict[str, LLMPort]`.
Calling `adapter.complete(..., timeout_s=X)` will fail pyright because
`LLMPort.complete()` has no `timeout_s` parameter. Two clean options:

1. **Preferred**: In `LLMRouter.complete()`, resolve the adapter and call
   it through the concrete type, not the protocol:
   ```python
   adapter = self._resolve(model)
   if hasattr(adapter, 'complete'):
       result = await adapter.complete(
           model, messages, tools=tools,
           temperature=temperature, max_tokens=max_tokens,
           tool_choice=tool_choice, timeout_s=timeout_s,
       )
   ```
   Since `_resolve()` returns the actual adapter instance (not `LLMPort`),
   you can cast: `cast(Any, adapter).complete(...)` or add a narrow
   `# type: ignore[call-arg]` at the call site.

2. **Alternative**: Set timeout as an adapter attribute before calling:
   ```python
   adapter._request_timeout_s = timeout_s  # set before call
   ```
   Then read it inside `complete()`. Avoids signature change entirely.

Use option 1 with `# type: ignore[call-arg]` — it's one comment per call
site and keeps the fix explicit. If we later add `timeout_s` to the
protocol (operator-approved), we just remove the ignores.

This is a prerequisite for both the asymmetric extraction experiment
(CPU/cloud archivist) and multi-provider parallelism (slow cloud
endpoints). See `wave_58_plan.md` "Post-Wave 58: Asymmetric Extraction
Experiment."

### Change 5: Adapter stream+tools safeguard (only if needed)

Do NOT add a speculative change unless you confirm a real caller is exposed
to the issue.

Current truth:

- `complete()` is already non-streaming
- colony runner uses `complete()` for tool-calling

Only change this adapter if you find a real path that combines:

- an Ollama Cloud endpoint
- tools present
- `stream=True`

If such a path exists, add the narrowest safeguard possible and document
why. If not, leave the adapter unchanged and say so in the summary.

## Tests / validation

### Host validation

Run from the host after setting keys:

```bash
python scripts/provider_benchmark.py
```

Record:

- which providers returned correct tool calls
- latency per provider
- which providers should be admitted to the registry

### Config / surface validation

After `docker compose up -d`, verify:

1. the app boots with the new registry entries
2. the cloud-endpoint surface shows the new cloud providers truthfully
3. no Ollama Cloud endpoint is probed as if it were a local `/health` server

### Timeout validation

Verify per-request timeout works:
1. Add a test registry entry with `time_multiplier: 3.0`
2. Confirm the adapter's httpx call uses 360s timeout (log or debug)
3. Confirm a `time_multiplier: 1.0` model still uses 120s (no regression)

### Concurrency confirmation

The extraction hooks (`_hook_memory_extraction`, `_hook_transcript_harvest`)
are fire-and-forget async tasks. The adapter's `_semaphore` at
`llm_openai_compatible.py:132` limits concurrent requests to local servers
(reads `LLM_SLOTS` env var). A single-slot CPU server queues requests at
the server level. Multiple extractions from sequential colonies queue
naturally. **No concurrency changes are needed** for the asymmetric
extraction experiment.

### Optional stream safeguard validation

Only if you changed `llm_openai_compatible.py` for stream+tools, prove
the caller exists and explain how the safeguard is exercised.

## Files owned

- `scripts/provider_benchmark.py`
- `config/formicos.yaml`
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/runtime.py` (LLMRouter timeout computation only)
- `src/formicos/adapters/llm_openai_compatible.py` (timeout parameterization
  + stream safeguard only if justified)

## Do not touch

- `src/formicos/core/ports.py` (LLMPort Protocol — contract file)
- `src/formicos/engine/context.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/eval/sequential_runner.py`
- Frontend component files

## Summary must include

- benchmark results by provider
- whether Ollama Cloud passed tool-calling compatibility
- which registry entries were added
- whether any cloud-provider surface truth bugs were fixed
- whether the adapter needed a real Ollama-specific stream safeguard or not
- confirmation that per-request timeout parameterization works (test with
  a `time_multiplier: 3.0` model and verify the httpx call uses 360s)
