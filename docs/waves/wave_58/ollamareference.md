# Ollama Cloud API integration reference for OpenAI-compatible adapters

**Ollama Cloud exposes a fully OpenAI-compatible endpoint at `https://ollama.com/v1/` using standard Bearer token auth**, making it a near drop-in replacement for any OpenAI adapter — but with critical caveats around tool calling reliability and GPU-time-based rate limits that diverge from token-counted systems. The API returns standard OpenAI response structures including `choices[0].message.content` and `tool_calls` arrays, uses SSE streaming with `delta.content`, and supports `/v1/chat/completions`, `/v1/completions`, and `/v1/models`. However, cloud tool calling suffered **500 errors through early March 2026** (GitHub #14542, now closed), and streaming combined with tools has historically dropped tool calls silently through the OpenAI compatibility layer.

---

## Endpoint configuration and authentication

The OpenAI-compatible base URL for direct cloud access is **`https://ollama.com/v1/`**. This is confirmed across Ollama's integration docs for OpenCode, Codex, and third-party tooling. The native Ollama API is at `https://ollama.com/api/` but for an OpenAI-compatible adapter, use the `/v1/` prefix exclusively.

Authentication uses a standard **`Authorization: Bearer <OLLAMA_API_KEY>`** header. API keys are created at `https://ollama.com/settings/keys`, do not expire, but can be revoked. The OpenAI Python SDK maps this naturally:

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://ollama.com/v1/",
    api_key=os.environ["OLLAMA_API_KEY"],
)
```

Supported endpoints on the cloud OpenAI-compatible layer:

| Endpoint | Cloud status |
|---|---|
| `POST /v1/chat/completions` | ✅ Fully supported |
| `POST /v1/completions` | ✅ Supported |
| `GET /v1/models` | ✅ Lists available cloud models |
| `GET /v1/models/{model}` | ✅ Supported |
| `POST /v1/responses` | ✅ Added v0.13.3, non-stateful only |
| `POST /v1/embeddings` | ❌ Returns 404 ("Coming soon") |
| `POST /v1/images/generations` | Unconfirmed on cloud |

**Model naming matters**: when calling the cloud API directly at `ollama.com/v1/`, use model names *without* the `-cloud` suffix (e.g., `gpt-oss:120b`, not `gpt-oss:120b-cloud`). The `-cloud` suffix is only used when routing cloud models through a local Ollama proxy.

---

## Request and response format compatibility

The `/v1/chat/completions` endpoint accepts all standard OpenAI parameters: `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `tools`, `tool_choice`, `response_format`, `stream`, `stream_options`, `frequency_penalty`, `presence_penalty`, `seed`, `stop`, `logit_bias`, `n`, `user`, plus Ollama additions like `reasoning_effort` (`"high"`, `"medium"`, `"low"`, `"none"`).

**Non-streaming responses** follow standard OpenAI structure exactly:

```json
{
  "id": "chatcmpl-914",
  "object": "chat.completion",
  "created": 1732871553,
  "model": "qwen3-coder:480b",
  "system_fingerprint": "fp_ollama",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "response text here",
      "tool_calls": [{
        "id": "call_rn5g1z57",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\": \"Tokyo\"}"
        }
      }]
    },
    "finish_reason": "stop"
  }]
}
```

All responses carry **`system_fingerprint: "fp_ollama"`** to identify origin. When the model invokes tools, `finish_reason` is `"tool_calls"`. The `arguments` field in tool calls is a **JSON string** (matching OpenAI's format), not a parsed object. Each tool call includes an auto-generated `id` and `type: "function"`. Tool responses should use `role: "tool"` with a matching `tool_call_id`.

**Streaming** uses standard OpenAI SSE format: `Content-Type: text/event-stream`, `data: {...}\n\n` chunks with `object: "chat.completion.chunk"` and `delta.content`, terminated by `data: [DONE]`. Token usage is available via `stream_options: {"include_usage": true}`.

**JSON mode** is supported via `response_format: {"type": "json_object"}` in the request.

---

## Error handling diverges from OpenAI's format

The OpenAI compatibility layer translates errors into **OpenAI's nested format**:

```json
{"error": {"message": "model not found", "type": "not_found_error"}}
```

Error type mapping: 400 → `invalid_request_error`, 404 → `not_found_error`, 500+ → `api_error`. However, the native Ollama API (`/api/`) uses a flat format: `{"error": "message string"}`. Mid-stream errors during SSE arrive as a JSON object in the stream while the HTTP status remains **200** — your adapter must check for `error` fields in streamed chunks.

Key HTTP status codes: **429** for rate limits (message: `"you've reached your hourly usage limit, please wait or upgrade to continue"`), **502** for cloud model gateway failures, **500** for internal errors. A `Retry-After` header on 429 responses is **not confirmed** in official docs — implement exponential backoff (1s, 2s, 4s, 8s) as the safe strategy.

---

## Cloud models available as of March 2026

Ollama Cloud hosts **30+ model variants** spanning multiple providers. Cloud models run at **native weights** (no quantization) on modern NVIDIA hardware. Below are the models most relevant to agentic tool-calling workloads:

| Model | Params | Context | Tools | Vision | Notes |
|---|---|---|---|---|---|
| **qwen3-coder:480b** | 480B MoE | 262K | ✅ | ❌ | Cloud-only at this size; flagship code model |
| **qwen3.5:397b** | 397B | 262K | ✅ | ✅ | Multimodal, thinking mode |
| **qwen3-vl:235b** | 235B | 262K | ✅ | ✅ | Vision-language flagship |
| **qwen3-next:80b** | 80B | 262K | ✅ | ❌ | Thinking support |
| **qwen3-coder-next** | Multiple | 262K | ✅ | ❌ | Optimized agentic coding |
| **gpt-oss:120b** | 120B | 131K | ✅ | ❌ | OpenAI's open-weight model |
| **gpt-oss:20b** | 20B | 131K | ✅ | ❌ | Smaller gpt-oss variant |
| **deepseek-v3.1:671b** | 671B MoE | 164K | ❌* | ❌ | Not tagged for tools |
| **deepseek-v3.2** | — | 164K | ❌* | ❌ | Improved reasoning variant |
| **minimax-m2.5** | — | 205K | ❌* | ❌ | Coding/agentic workflows |
| **minimax-m2.1** | — | 205K | ❌* | ❌ | Multilingual code |
| **minimax-m2** | — | 205K | ❌* | ❌ | Agentic workflows |
| **glm-5** | 744B MoE (40B active) | 203K | ❌* | ❌ | By Z.ai; strong reasoning |
| **kimi-k2:1t** | ~1T | 262K | ❌* | ❌ | Moonshot AI's large model |
| **kimi-k2.5** | — | 262K | ❌* | ❌ | Multimodal agentic |
| **gemini-3-flash-preview** | — | **1.0M** | ❌** | ❌ | Google; broken tool calling (400) |
| **gemini-3-pro-preview** | — | **1.0M** | ✅ | ✅ | Premium model pool; Max plan |
| **devstral-2:123b** | 123B | 262K | ✅ | ❌ | Mistral; multi-file code editing |
| **nemotron-3-nano:30b** | 30B | **1.0M** | ✅ | ❌ | NVIDIA; efficient agentic |
| **cogito-2.1:671b** | 671B | 164K | ❌* | ❌ | MIT licensed |

*❌\* = not tagged for tools on Ollama's cloud page but may still work if the underlying model supports it. Ollama states cloud models "trained to support tools are tested for tool calling before they go live."*

*❌\*\* = Gemini 3 Flash tool calling returns 400 due to `thought_signature` propagation bug (GitHub #14567).*

For reliable tool calling, **prioritize Qwen3 family models** (qwen3-coder:480b, qwen3.5:397b, qwen3-next:80b) and **gpt-oss** variants, which are explicitly tagged and tested for tools. DeepSeek models lack official tool tagging on cloud. Llama models are **not available** as cloud models.

---

## Tool calling: the critical integration risk

This is the most important section for an agentic adapter. Three distinct problems affect tool calling on Ollama Cloud:

**Problem 1: Cloud tool calling 500 errors.** As of early March 2026, sending *any* tool definitions to cloud models triggered HTTP 500 (GitHub #14542). The issue is now **closed**, suggesting a fix was deployed, but community reports from mid-March still referenced intermittent failures. Test tool calling against your target model before relying on it in production.

**Problem 2: Streaming silently drops tool calls.** The OpenAI compatibility layer has a long history of dropping tool calls when `stream: true` is set. The model decides to invoke a tool, but the streaming response returns empty content with `finish_reason: "stop"`, losing the tool call entirely. This is tracked across issues #7881, #9632, #12557, and #5796. **The workaround is mandatory: always set `stream: false` when tools are present.** Ollama's native `/api/chat` endpoint handles streaming + tools correctly since May 2025, but the `/v1/` compat layer has lagged behind.

**Problem 3: Model-specific failures.** Gemini 3 Flash cloud returns 400 on tool calls due to a missing `thought_signature` in function call parts (GitHub #14567). DeepSeek-R1 smaller variants explicitly error with "does not support tools." Always verify tool calling works for your specific model before integrating.

**Practical recommendation for an adapter**: Set `stream: false` unconditionally when the request includes tools. Implement a tool-call validation step that checks whether `choices[0].message.tool_calls` exists and contains properly structured entries before processing. Implement retry logic with exponential backoff for 500 errors, with a fallback to a different model if a specific model's tool calling is broken.

---

## Rate limits are GPU-time-based, not token-based

Ollama Cloud measures usage by **GPU compute time**, not fixed token or request counts. This means limits depend on model size and request duration — a 480B model consumes far more budget than a 20B model for the same token count. Ollama explicitly states: **"Ollama doesn't cap you at a set number of tokens."**

| Plan | Price | Session reset | Weekly reset | Concurrency | Relative usage |
|---|---|---|---|---|---|
| Free | $0 | 5 hours | 7 days | 1 model | Baseline |
| Pro | $20/mo | 5 hours | 7 days | 3 models | **50× Free** |
| Max | $100/mo | 5 hours | 7 days | 10 models | **250× Free** |

Limits are **global across all models**, not per-model. At **90% of limits**, Ollama sends an email alert. Exact GPU-time budgets are not published — Ollama uses qualitative descriptions: "light usage" (Free), "day-to-day work" (Pro), "heavy sustained usage" (Max). There is no per-token pricing currently, though **"competitive per-token rates, including cache-aware pricing"** are described as coming soon.

**Feasibility for ~24 LLM calls per task** (~2K input + ~1K output each, ~72K total tokens): On smaller models (20B-30B), this likely fits within a single free-tier session. On medium models (120B), it may approach session limits. On large models (480B, 671B), the free tier will likely exhaust quickly. The **1-concurrent-model limit** on free tier means all calls must be sequential. Pro tier with 3 concurrent slots and 50× usage is the practical minimum for regular agentic workloads with large models.

When rate limited, requests beyond the concurrency limit are **queued** until a slot opens. If the queue is full, the request is **rejected** with HTTP 429.

---

## Cloud versus local Ollama: key adapter differences

| Aspect | Local (`localhost:11434`) | Cloud (`ollama.com`) |
|---|---|---|
| OpenAI compat base URL | `http://localhost:11434/v1/` | `https://ollama.com/v1/` |
| Authentication | None required | `Bearer $OLLAMA_API_KEY` |
| Model naming | Add `-cloud` suffix for cloud models | No suffix needed |
| `/v1/embeddings` | ✅ Works | ❌ 404 |
| Default context window | **2048 tokens** (must configure) | Full model context |
| `num_ctx` / `options` | Configurable via request | Not applicable / server-set |
| `keep_alive` | Controls model memory lifetime | Not applicable |
| Rate limits | None | GPU-time-based per plan |
| Model management | Pull, push, create, delete | Read-only (list via `/v1/models`) |

The most critical difference for adapter code: **cloud models run at full context length automatically**, while local Ollama defaults to a dangerously low **2048 tokens** and silently truncates content when exceeded. If your adapter supports both local and cloud, you must set `num_ctx` via the native API `options` field for local deployments, or use a Modelfile — there is no way to set context size through the OpenAI-compatible `/v1/` endpoints.

The `/v1/models` endpoint works on cloud and returns available cloud models. Cloud-only models (largest parameter counts like qwen3-coder:480b, glm-5:744b) cannot be downloaded for local use.

---

## Conclusion

Ollama Cloud's OpenAI compatibility layer is architecturally sound — the endpoint structure, auth pattern, and response schemas align with OpenAI's API closely enough for most adapters to work with minimal configuration changes. The core integration is straightforward: point your base URL to `https://ollama.com/v1/`, set the API key, and choose a model. **The Qwen3 family and gpt-oss models are the strongest choices for tool-calling workloads**, combining explicit tool support with tested cloud deployment.

The two non-negotiable implementation requirements are: **disable streaming when tools are present** (`stream: false`) and **implement robust retry logic with exponential backoff** for 500/429 responses. The cloud platform experienced measurable reliability issues in early-to-mid March 2026, with tool calling 500 errors and service degradation reported by multiple users. These issues appear to be resolving, but defensive coding is essential. Monitor the error response's `type` field (`api_error`, `invalid_request_error`) to distinguish transient cloud failures from permanent configuration errors, and consider maintaining a fallback model list (e.g., fall from qwen3-coder:480b to gpt-oss:120b) for resilience.