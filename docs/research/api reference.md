# LLM API model reference: seven providers compared

**The fastest way to ship LLM features is knowing exactly which model to call, what it costs, and how to call it.** This reference covers every current production model from seven complementary providers—OpenAI, Anthropic, Google Gemini, MiniMax, DeepSeek, Mistral (recommended for code-heavy work), and Groq (recommended for cost-efficient high-throughput)—with exact API strings, pricing, and call examples verified against official documentation. Two additional providers were selected to fill gaps: Mistral for its unique FIM-capable Codestral and top-scoring Devstral agentic coding models, and Groq for **5–10× faster inference** than GPU-based providers via custom LPU hardware.

> **Last verified: March 24, 2026.** Pricing and model availability change frequently. Always confirm against each provider's official pricing page before committing to production.

---

## 1. OpenAI

| Property | Value |
|---|---|
| **API base URL** | `https://api.openai.com/v1/` |
| **Authentication** | `Authorization: Bearer $OPENAI_API_KEY` |
| **SDKs** | Python: `openai` · Node: `openai` · .NET: official NuGet package |
| **OpenAI-compatible** | N/A (is the standard) |
| **Batch API** | ✅ 50% off, 24-hour window |
| **Prompt caching** | ✅ Automatic; **90% off** input for GPT-5.x, ~50–75% off for GPT-4.x |

### Current models

| Model ID | Context | Max output | Input $/1M | Output $/1M | Cached input $/1M | Capabilities |
|---|---|---|---|---|---|---|
| `gpt-5.4` | 1,050K | 128K | $2.50 (short) / $5.00 (>272K) | $15.00 / $22.50 | $0.25 / $0.50 | Vision, tools, reasoning (`reasoning.effort`) |
| `gpt-5.4-mini` | 400K | 128K | $0.75 | $4.50 | $0.075 | Vision, tools, reasoning |
| `gpt-5.4-nano` | 400K | 128K | $0.20 | $1.25 | $0.02 | Vision, tools, lightweight reasoning |
| `gpt-4.1` | 1,048K | 32K | $2.00 | $8.00 | $0.50 | Vision, tools — no reasoning |
| `gpt-4.1-mini` | 1,048K | 32K | $0.40 | $1.60 | $0.04 | Vision, tools — no reasoning |
| `gpt-4.1-nano` | 1,048K | 32K | $0.10 | $0.40 | $0.01 | Vision, tools — no reasoning |
| `o3` | 200K | 100K | $2.00 | $8.00 | $1.00 | Reasoning-first, vision, tools |
| `o4-mini` | 200K | 100K | $1.10 | $4.40 | $0.275 | Reasoning-first, vision, tools |
| `o3-pro` | 200K | 100K | $20.00 | $80.00 | — | Deep reasoning, highest accuracy |
| `gpt-4o` | 128K | 16K | $2.50 | $10.00 | $1.25 | Vision, tools (legacy, still active) |
| `gpt-4o-mini` | 128K | 16K | $0.15 | $0.60 | $0.075 | Vision, tools (legacy, still active) |

*GPT-5.4 and GPT-5.4-pro apply **2× input / 1.5× output** pricing for the entire session when input exceeds 272K tokens. GPT-4.5, GPT-4-turbo, and GPT-3.5-turbo are deprecated.*

```python
from openai import OpenAI
client = OpenAI()  # reads OPENAI_API_KEY

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "developer", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in one paragraph."},
    ],
)
print(response.choices[0].message.content)
```

**Practical notes.** Reasoning tokens (o-series and GPT-5.4 with reasoning enabled) are **billed as output tokens**—a short visible answer can consume 10,000+ thinking tokens. Use `reasoning.effort` (none/low/medium/high) to control this. The `"developer"` role replaces the older `"system"` role for instruction prompts. OpenAI also offers a newer Responses API alongside Chat Completions; both are supported indefinitely.

---

## 2. Anthropic

| Property | Value |
|---|---|
| **API base URL** | `https://api.anthropic.com/v1/messages` |
| **Authentication** | `x-api-key: $ANTHROPIC_API_KEY` + `anthropic-version: 2023-06-01` |
| **SDKs** | Python: `anthropic` · TypeScript: `@anthropic-ai/sdk` |
| **OpenAI-compatible endpoint** | ❌ No (use LiteLLM or Vercel AI Gateway to translate) |
| **Batch API** | ✅ 50% off all token costs; stacks with caching |
| **Prompt caching** | ✅ 5-min write at 1.25× input; 1-hr write at 2× input; **read at 0.10× input** |

### Current models

| Model ID | Context | Max output | Input $/1M | Output $/1M | Cache read $/1M | Capabilities |
|---|---|---|---|---|---|---|
| `claude-opus-4-6` | 1M | 128K | $5.00 | $25.00 | $0.50 | Vision, tools, adaptive extended thinking |
| `claude-sonnet-4-6` | 1M | 64K | $3.00 | $15.00 | $0.30 | Vision, tools, adaptive extended thinking |
| `claude-haiku-4-5` | 200K | 64K | $1.00 | $5.00 | $0.10 | Vision, tools, extended thinking |
| `claude-opus-4-5` | 200K | 64K | $5.00 | $25.00 | $0.50 | Vision, tools, extended thinking |
| `claude-sonnet-4-5` | 200K | 64K | $3.00 | $15.00 | $0.30 | Vision, tools, extended thinking |
| `claude-sonnet-4` | 200K | 8K (128K via beta) | $3.00 | $15.00 | $0.30 | Vision, tools, extended thinking |
| `claude-3-5-haiku-20241022` | 200K | 8K | $0.80 | $4.00 | $0.08 | Vision, tools — no extended thinking |

*Sonnet 4/4.5 can access 1M context via the `context-1m-2025-08-07` beta header (Tier 4+ orgs only; inputs >200K billed at $6/$22.50). Opus 4/4.1 default to 8K max output; use the `output-128k-2025-02-19` beta header to unlock 128K. Claude 3.7 Sonnet, Claude 3 Opus, and older models are deprecated.*

```python
import anthropic
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, Claude!"}],
)
print(response.content[0].text)
```

**Practical notes.** Extended thinking tokens are billed at the **standard output rate** with no separate pricing tier. Use the `effort` parameter (low/medium/high/max) on 4.5+ models to control reasoning cost. On Opus 4.6 and Sonnet 4.6, `thinking: {type: "adaptive"}` is recommended—the model decides autonomously when to reason. Prompt caching pays for itself after **a single cache read** on the 5-minute tier, making it essential for any repeated system prompts or reference documents.

---

## 3. Google Gemini

| Property | Value |
|---|---|
| **API base URL** | `https://generativelanguage.googleapis.com/v1beta/` |
| **Authentication** | API key via `x-goog-api-key` header or `?key=` param |
| **SDKs** | Python: `google-genai` · JS: `@google/genai` · Go: `google.golang.org/genai` |
| **OpenAI-compatible endpoint** | ✅ `https://generativelanguage.googleapis.com/v1beta/openai/` |
| **Batch API** | ✅ 50% off, 24-hour window |
| **Context caching** | ✅ ~75–90% off cached input; storage $1.00–$4.50/1M tokens/hour |

### Current models

| Model ID | Context | Max output | Input $/1M | Output $/1M | Free tier | Capabilities |
|---|---|---|---|---|---|---|
| `gemini-3.1-pro-preview` | 1M | 65K | $2.00 (≤200K) / $4.00 (>200K) | $12.00 / $18.00 | ❌ | Vision, tools, thinking levels |
| `gemini-3-flash-preview` | 1M | 65K | $0.50 | $3.00 | ✅ | Vision, tools, thinking levels |
| `gemini-3.1-flash-lite-preview` | 1M | 65K | $0.25 | $1.50 | ✅ | Vision, tools, thinking levels |
| `gemini-2.5-pro` | 1M | 65K | $1.25 (≤200K) / $2.50 (>200K) | $10.00 / $15.00 | ✅ (5 RPM) | Vision, tools, thinking budget |
| `gemini-2.5-flash` | 1M | 65K | $0.30 | $2.50 | ✅ (10 RPM) | Vision, tools, hybrid thinking |
| `gemini-2.5-flash-lite` | 1M | 65K | $0.10 | $0.40 | ✅ (15 RPM) | Vision, tools, optional thinking |

*Free tier: no credit card required, 250K TPM, content may be used to improve Google products. `gemini-2.0-flash` and `gemini-2.0-flash-lite` are deprecated (sunset June 1, 2026). The legacy `google-generativeai` SDK is deprecated; use `google-genai`.*

**Free tier rate limits (paid Tier 1 removes most caps):**

| Model | Free RPM | Free RPD | Free TPM |
|---|---|---|---|
| `gemini-2.5-pro` | 5 | 100 | 250,000 |
| `gemini-2.5-flash` | 10 | 250 | 250,000 |
| `gemini-2.5-flash-lite` | 15 | 1,000 | 250,000 |

```python
from google import genai
client = genai.Client()  # reads GEMINI_API_KEY

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain how transformers work in 3 sentences.",
)
print(response.text)
```

**Practical notes.** Google's free tier is **the most generous among major providers**—no credit card, no expiration, full 1M context, access to 5+ models including Gemini 2.5 Pro. However, thinking tokens are billed as output tokens on all 2.5 and 3.x models, so actual costs can far exceed naive output estimates. Set `thinking_level="low"` or `"minimal"` for cost-sensitive workloads. Gemini 3 models return `thoughtSignature` fields that must be echoed back in multi-turn conversations; SDKs handle this automatically.

---

## 4. MiniMax

| Property | Value |
|---|---|
| **API base URL (OpenAI-compat)** | `https://api.minimax.io/v1` |
| **API base URL (Anthropic-compat)** | `https://api.minimax.io/anthropic` (recommended) |
| **Authentication** | `Authorization: Bearer $MINIMAX_API_KEY` |
| **SDKs** | Use Anthropic SDK (recommended) or OpenAI SDK — no proprietary SDK |
| **OpenAI-compatible endpoint** | ✅ Yes |
| **Batch API** | Not documented |
| **Prompt caching** | ✅ Cache reads 80–90% cheaper than standard input |

### Current models

| Model ID | Context | Max output | Input $/1M | Output $/1M | Cache read $/1M | Cache write $/1M | Capabilities |
|---|---|---|---|---|---|---|---|
| `MiniMax-M2.7` | 205K | ~128K (incl. CoT) | $0.30 | $1.20 | $0.06 | $0.375 | Reasoning, tools — no vision |
| `MiniMax-M2.7-highspeed` | 205K | ~128K (incl. CoT) | $0.60 | $2.40 | $0.06 | $0.375 | Same capabilities, ~2× faster |
| `MiniMax-M2.5` | 197K | 65K | $0.30 | $1.20 | $0.03 | $0.375 | Reasoning, tools — no vision |
| `MiniMax-M2.5-highspeed` | 197K | 65K | $0.60 | $2.40 | $0.03 | $0.375 | Same capabilities, ~2× faster |

*M2.5 is open-weight (Hugging Face). M2.7 launched March 18, 2026. Highspeed variants are identical in capability at 2× the price for ~2× faster inference. No free tier documented. No vision support on current text models.*

```python
import anthropic
client = anthropic.Anthropic(
    base_url="https://api.minimax.io/anthropic",
    api_key="your-minimax-api-key",
)
message = client.messages.create(
    model="MiniMax-M2.7",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Explain TCP vs UDP in 3 sentences."}],
)
print(message.content[0].text)
```

**Practical notes.** MiniMax recommends the Anthropic-compatible endpoint over the OpenAI-compatible one because it provides full access to interleaved thinking (reasoning tokens via the `thinking` parameter). To enable reasoning via the OpenAI SDK, pass `extra_body={"reasoning_split": True}`. Cache read pricing of **$0.03–$0.06/M** against a $0.30/M base input rate makes prompt caching essential for cost optimization on repetitive workloads.

---

## 5. DeepSeek

| Property | Value |
|---|---|
| **API base URL** | `https://api.deepseek.com` (also `https://api.deepseek.com/v1`) |
| **Authentication** | `Authorization: Bearer $DEEPSEEK_API_KEY` |
| **SDKs** | Use OpenAI SDK — no proprietary SDK needed |
| **OpenAI-compatible** | ✅ Fully compatible (also supports Anthropic API format) |
| **Batch API** | ❌ Not available |
| **Prompt caching** | ✅ Automatic disk-based; **90% off** cached input; free storage |

### Current models

DeepSeek offers only **two model IDs**, both backed by DeepSeek-V3.2 (671B MoE, ~37B active):

| Model ID | Mode | Context | Max output (default / max) | Input $/1M | Cached input $/1M | Output $/1M | Capabilities |
|---|---|---|---|---|---|---|---|
| `deepseek-chat` | Non-thinking | 128K | 4,096 / 8,192 | $0.28 | $0.028 | $0.42 | Tools, JSON mode, FIM (beta) — no vision |
| `deepseek-reasoner` | Thinking | 128K | 32,768 / 65,536 | $0.28 | $0.028 | $0.42 | Tools, JSON mode, visible CoT — no vision |

*Pricing is identical for both models. Thinking/reasoning tokens in `deepseek-reasoner` are billed at the output rate. Off-peak pricing was discontinued September 2025. New users receive **5M free tokens** (no credit card required). DeepSeek states it does "NOT constrain user's rate limit."*

```python
from openai import OpenAI
client = OpenAI(
    api_key="your-deepseek-key",
    base_url="https://api.deepseek.com",
)
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum entanglement in 3 sentences."},
    ],
)
print(response.choices[0].message.content)
```

**Practical notes.** DeepSeek's automatic prefix caching is its **killer cost feature**—at $0.028/M for cached input, effective costs drop to roughly 10× cheaper than the already-low base rate. Structure prompts with static content (system prompts, tool definitions, few-shot examples) first and variable content last to maximize prefix matches. Real-world users report 50–70%+ cache hit rates with minimal optimization. Migration from OpenAI requires changing only `base_url` and `api_key`—all SDK features work identically.

---

## 6. Mistral — recommended for code-heavy workloads

Mistral is the only provider with a **full-stack coding ecosystem**: Codestral (dedicated FIM code completion), Devstral 2 (72.2% SWE-bench Verified, top open-weight agentic coder), Codestral Embed (code-specific embeddings), and Mistral Small 4 (unified reasoning+vision+code in one model).

| Property | Value |
|---|---|
| **API base URL** | `https://api.mistral.ai/v1` |
| **Authentication** | `Authorization: Bearer $MISTRAL_API_KEY` |
| **SDKs** | Python: `mistralai` · JS: `@mistralai/mistralai` |
| **OpenAI-compatible** | ✅ Yes — usable with OpenAI SDK |
| **Batch API** | ✅ via `/v1/batch/jobs` (JSONL format) |
| **Prompt caching** | ❌ No explicit cached-token pricing discount |

### Code-specialist models

| Model ID | Context | Input $/1M | Output $/1M | FIM | Vision | Reasoning | Notes |
|---|---|---|---|---|---|---|---|
| `codestral-2508` (alias: `codestral-latest`) | 256K | $0.30 | $0.90 | ✅ | ❌ | ❌ | Low-latency FIM, 80+ languages |
| `devstral-2512` (alias: `devstral-latest`) | 262K | $0.40 | $2.00 | ❌ | ✅ | ❌ | 123B dense; **72.2% SWE-bench**; Apache 2.0 |
| `labs-devstral-small-2512` | 256K | $0.10 | $0.30 | ❌ | ✅ | ❌ | 24B; 68% SWE-bench; runs on single RTX 4090 |

### Generalist and efficient models

| Model ID | Context | Input $/1M | Output $/1M | Vision | Tools | Reasoning | Notes |
|---|---|---|---|---|---|---|---|
| `mistral-small-2603` (alias: `mistral-small-latest`) | 262K | $0.15 | $0.60 | ✅ | ✅ | ✅ (`reasoning_effort`) | 119B MoE; Apache 2.0; also supports FIM |
| `mistral-large-2512` (alias: `mistral-large-latest`) | 262K | $0.50 | $1.50 | ✅ | ✅ | ❌ | 675B MoE flagship; Apache 2.0 |
| `ministral-8b-2512` | 262K | $0.15 | $0.15 | ✅ | ✅ | ❌ | Ultra-cheap edge model |
| `ministral-3b-2512` | 131K | $0.10 | $0.10 | ✅ | ✅ | ❌ | Smallest; routing/classification |

*Free "Experiment" tier available on all models (rate-limited, no credit card). A dedicated `codestral.mistral.ai` endpoint offers free Codestral access for IDE use (phone verification required).*

```python
from mistralai import Mistral
import os

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

# Chat completion
response = client.chat.complete(
    model="codestral-latest",
    messages=[{"role": "user", "content": "Write an async Python web scraper with error handling"}],
)
print(response.choices[0].message.content)

# Fill-in-the-Middle (unique to Codestral)
fim = client.fim.complete(
    model="codestral-latest",
    prompt="def fibonacci(n: int):",
    suffix="print(fibonacci(10))",
)
print(fim.choices[0].message.content)
```

**Practical notes.** Use a **3-model routing strategy** for code workloads: `codestral-latest` for autocomplete/FIM (lowest latency), `devstral-2512` for multi-file agentic SWE tasks (highest SWE-bench), and `mistral-small-2603` as a versatile fallback that handles reasoning + vision + coding in one endpoint. Mistral's coding models are significantly cheaper than competitors at equivalent quality—Codestral at $0.30/$0.90 and Devstral Small at $0.10/$0.30 are among the cheapest high-quality code models available.

---

## 7. Groq — recommended for cost-efficient, high-throughput workloads

Groq offers **5–10× faster inference** than GPU-based providers via custom LPU (Language Processing Unit) hardware, at competitive or below-market prices. This fills a unique speed+cost niche that no other provider in the lineup covers.

| Property | Value |
|---|---|
| **API base URL** | `https://api.groq.com/openai/v1` |
| **Authentication** | `Authorization: Bearer $GROQ_API_KEY` |
| **SDKs** | Python: `groq` · JS: `groq-sdk` · also works with OpenAI SDK |
| **OpenAI-compatible** | ✅ Fully compatible |
| **Batch API** | ✅ 50% off, 24-hour to 7-day window |
| **Prompt caching** | ✅ Automatic; 50% off input for cached prefixes; 2-hour TTL |

### Notable models

| Model ID | Speed (tok/s) | Context | Max output | Input $/1M | Output $/1M | Capabilities |
|---|---|---|---|---|---|---|
| `openai/gpt-oss-20b` | **~1,000** | 131K | 65K | $0.075 | $0.30 | Fastest model; reasoning capable |
| `openai/gpt-oss-120b` | ~500 | 131K | 65K | $0.15 | $0.60 | Flagship quality; reasoning, tools |
| `llama-3.3-70b-versatile` | ~280 | 131K | 32K | $0.59 | $0.79 | High-quality open-source; tool calling |
| `llama-3.1-8b-instant` | ~560 | 131K | 131K | $0.05 | $0.08 | Ultra-cheap; classification, routing |
| `meta-llama/llama-4-scout-17b-16e-instruct` | ~750 | 131K | 8K | $0.11 | $0.34 | Multimodal (vision), MoE |
| `moonshotai/kimi-k2-instruct-0905` | ~200 | 262K | 16K | $1.00 | $3.00 | Largest context; 1T MoE; strong agentic coding |

*Free tier: no credit card, **30 RPM**, 14,400 requests/day on 8B, 1,000/day on larger models. Prompt caching and batch discounts do NOT stack.*

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)
response = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "Explain quantum computing briefly."}],
)
print(response.choices[0].message.content)
```

**Practical notes.** The `openai/gpt-oss-20b` model is the **sweet spot** for most throughput workloads—it is simultaneously the fastest (~1,000 tok/s) and among the cheapest ($0.075/$0.30) models on the platform, with reasoning capabilities. Only step up to `gpt-oss-120b` when you need higher intelligence. Groq's automatic prompt caching requires zero code changes; keep static content (system prompts, tool definitions) at the beginning of messages to maximize the 50% input discount.

---

## Cross-provider comparison of flagship models

This table compares each provider's best general-purpose model side by side:

| Provider | Flagship model ID | Context | Max output | Input $/1M | Output $/1M | Cached input $/1M | Batch discount | Key differentiator |
|---|---|---|---|---|---|---|---|---|
| **OpenAI** | `gpt-5.4` | 1,050K | 128K | $2.50 | $15.00 | $0.25 | 50% | Largest context + output; integrated reasoning effort control |
| **Anthropic** | `claude-opus-4-6` | 1M | 128K | $5.00 | $25.00 | $0.50 | 50% | Adaptive extended thinking; strongest agentic tool use |
| **Gemini** | `gemini-2.5-pro` | 1M | 65K | $1.25 | $10.00 | $0.125 | 50% | Generous free tier; multimodal native; cheapest frontier model |
| **MiniMax** | `MiniMax-M2.7` | 205K | ~128K | $0.30 | $1.20 | $0.06 | — | Ultra-cheap reasoning; both OpenAI + Anthropic compatible |
| **DeepSeek** | `deepseek-chat` | 128K | 8K | $0.28 | $0.42 | $0.028 | — | Lowest absolute pricing; automatic 90% cache discount |
| **Mistral** | `codestral-2508` | 256K | 256K | $0.30 | $0.90 | — | ✅ | Only FIM-capable API model; 80+ language code specialist |
| **Groq** | `openai/gpt-oss-20b` | 131K | 65K | $0.075 | $0.30 | $0.0375 | 50% | ~1,000 tok/s; 5–10× faster than GPU providers |

### Quick decision guide for cost-sensitive models

| Provider | Cheapest model ID | Input $/1M | Output $/1M | Best for |
|---|---|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | $0.05 | $0.08 | Routing, classification at extreme speed |
| **DeepSeek** | `deepseek-chat` (cached) | $0.028 | $0.42 | Cheapest smart model with caching |
| **Gemini** | `gemini-2.5-flash-lite` | $0.10 | $0.40 | Free tier available; 1M context |
| **OpenAI** | `gpt-4.1-nano` | $0.10 | $0.40 | 1M context at rock-bottom cost |
| **Mistral** | `ministral-3b-2512` | $0.10 | $0.10 | Cheapest equal input/output pricing |
| **MiniMax** | `MiniMax-M2.5` | $0.30 | $1.20 | Cheapest with full reasoning chain |
| **Anthropic** | `claude-3-5-haiku-20241022` | $0.80 | $4.00 | Cheapest Claude with vision+tools |

---

## What every model shares and where they diverge

All seven providers now support **streaming SSE responses and tool/function calling**. Six of seven offer OpenAI-compatible endpoints (Anthropic is the exception). Five of seven offer batch APIs with a standard **50% discount** (DeepSeek and MiniMax do not). Prompt caching is available from six providers, but implementations vary significantly: OpenAI and DeepSeek offer automatic prefix caching, Anthropic requires explicit `cache_control` markers, Google charges hourly storage fees, and Mistral does not offer cached-token discounts at all.

The largest divergence is in **reasoning token billing transparency**. OpenAI, Anthropic, Google, and DeepSeek all bill thinking/reasoning tokens as output tokens with no separate rate—but only Anthropic and OpenAI expose granular controls (`effort` parameter, `reasoning.effort`, `thinking_budget`) to cap reasoning costs. Developers building cost-sensitive reasoning pipelines should set these controls explicitly rather than relying on defaults, which tend toward maximum reasoning depth.

Context window sizes have converged around **1M tokens** for frontier models (OpenAI, Anthropic, Gemini), while mid-tier providers (MiniMax, DeepSeek, Groq) cluster around **128–262K tokens**. Max output has settled at **64–128K tokens** for flagship models, with DeepSeek as the notable outlier capping at just 8K (chat) or 65K (reasoner).

For developers choosing between providers: **DeepSeek** offers the lowest absolute cost per token with strong quality. **Groq** is unmatched for latency-sensitive applications. **Gemini** provides the best free tier for prototyping. **Mistral** is the clear choice for dedicated code tooling. **OpenAI** and **Anthropic** compete for highest capability, with OpenAI winning on context size and Anthropic on agentic reliability. **MiniMax** offers a compelling middle ground with dual API compatibility and aggressive pricing.