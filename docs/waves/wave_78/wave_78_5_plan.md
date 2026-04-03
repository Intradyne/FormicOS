# Wave 78.5 Plan: Swarm Experiment Fixes + Security Hardening

**Theme:** Fix the two blocking issues that prevented the swarm experiment
from running (Qwen3.5 Jinja template parser + Gemini 400 errors), fix
the cosmetic event replay error, and frontload two low-risk security items.

**Teams:** 3 independent tracks. No merge-order dependency.

**Estimated total change:** ~210 new lines, ~30 changed lines.

**Research basis:** Live swarm experiment failure logs (29 Mar 2026),
codebase audit of tool schemas, adapter code, and event model, plus
official Gemini OpenAI-compat docs.

---

## Root cause analysis

### The Qwen3.5 Jinja template parser failure

The swarm experiment failed at every local llama.cpp tool call. Both the
35B Queen and 4B swarm workers returned HTTP 400 with:

```text
Unable to generate parser for this template. Automatic parser generation
failed: While executing CallExpression at line 85, column 32 in source...
```

**Root cause:** llama.cpp's Jinja template engine cannot parse certain
constructs in the Qwen3.5 GGUF-embedded chat template when processing
tool schemas that contain `items: {type: "object", properties: {...}}`
patterns. Synthetic tools with flat schemas work fine; the parser chokes
specifically on nested object-in-array schemas.

**5 tool schemas trigger the bug** (verified by codebase grep):

| Tool | File | Line | Parameter | What triggers it |
|------|------|------|-----------|------------------|
| `spawn_colony` | `queen_tools.py` | 364 | `castes` | array of `{caste, tier, count}` objects |
| `spawn_parallel` | `queen_tools.py` | 489 | `tasks` | array of `{task_id, task, caste, ...}` objects |
| `define_workflow_steps` | `queen_tools.py` | 948 | `steps` | array of `{description, expected_outputs, ...}` objects |
| `propose_plan` | `queen_tools.py` | 1000 | `options` | array of `{label, description, colonies}` objects |
| `patch_file` | `tool_dispatch.py` | 393 | `operations` | array of `{search, replace}` objects |

### The Gemini 400 error

The native Gemini adapter (`llm_gemini.py`) passes tool parameter schemas
through unmodified to the native Gemini API. `_build_tools()` wraps them
as `functionDeclarations` but does not transform OpenAI-style schemas into
Gemini-specific shapes. The same nested array-of-object patterns that work
through the OpenAI-compatible path are the likely cause of the native 400s.

**Important nuance:** the existing OpenAI-compatible adapter already treats
tool schemas as opaque JSON and is used for many cloud providers
successfully. Anthropic also accepts the rich schemas as-is through its own
adapter. There is no evidence in the current codebase that OpenAI-compatible
cloud providers or Anthropic need flattening.

**Verified fix path:** Gemini's OpenAI-compatible endpoint at
`https://generativelanguage.googleapis.com/v1beta/openai/` accepts the
standard OpenAI tool-calling payload shape, including function tools.
This is documented by Google and was also verified live during the swarm
debugging session.

### The ServiceTriggerFired replay error

`ServiceTriggerFired` at `core/events.py:1382` uses `FrozenConfig`, which
has `extra="forbid"`. A persisted event from the proactive-intelligence
addon includes a `handler` field that the model does not declare. Every
replay logs a validation error. Cosmetic, but noisy.

### The security hardening scope

Two security items are low-risk enough to frontload here:

1. Drop a few unused Docker capabilities from the `formicos` container.
2. Validate model endpoints against metadata/special-case targets at
   startup.

The second item must stay truly low-risk. The live registry still supports:

- localhost endpoints in non-Docker dev (`http://localhost:8008`)
- Docker service names in Compose (`http://llm:8080`, `http://qdrant:6333`)
- private/LAN endpoints for self-hosted gateways and proxies

So this wave should not block all RFC1918 / loopback addresses.

---

## Track 1: Provider-Aware Tool Schema Sanitization

### What to build

**`src/formicos/engine/schema_sanitize.py` (~60 lines NEW)**

Add a pure helper that flattens nested array-of-object schemas into
array-of-string fields with descriptive text and an inline JSON example.
This keeps the tool contract understandable to the model while avoiding
the nested schema shape that breaks local llama.cpp parsing.

```python
def sanitize_tool_schemas(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_sanitize_one(copy.deepcopy(s)) for s in specs]

def maybe_sanitize_tool_schemas(
    provider: str,
    specs: Sequence[dict[str, Any]] | None,
) -> Sequence[dict[str, Any]] | None:
    if not specs:
        return specs
    if provider in {"llama-cpp", "llama-cpp-swarm", "gemini"}:
        return sanitize_tool_schemas(list(specs))
    return specs

def coerce_array_items(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                result.append(parsed)
    return result
```

The helper is pure dict transformation. No surface imports, no adapter
imports, no runtime state.

### Where to hook it

**Hook once at the adapter boundary in `surface/runtime.py` `complete()`.**

Both Queen and colony tool calls flow through `LLMRouter.complete()`.
Two sanitization call sites:

**Site 1 - primary adapter call**

Before `adapter.complete()`, sanitize using the prefix extracted from
`model.split("/", 1)[0]`.

```python
_tools = maybe_sanitize_tool_schemas(prefix, tools)
result = await adapter.complete(
    model, messages, tools=_tools,
    ...
)
```

**Site 2 - fallback adapter call**

Inside `_complete_with_fallback()`, before `fb_adapter.complete()`,
sanitize using `fb_prefix`.

```python
_fb_tools = maybe_sanitize_tool_schemas(fb_prefix, tools)
result = await fb_adapter.complete(
    fallback_model, messages, tools=_fb_tools,
    ...
)
```

That keeps the transform provider-aware:

- sanitize for `llama-cpp` and `llama-cpp-swarm` (confirmed failure path)
- sanitize for native `gemini` if that provider remains in use
- keep `anthropic`, `openai`, and other OpenAI-compatible cloud providers
  on the rich schemas they already handle correctly

**Also fix `extra_body` forwarding** while touching this function.
The current exact-match check for `prefix == "llama-cpp"` excludes
`llama-cpp-swarm`. Change it to `prefix.startswith("llama-cpp")` so
thinking-mode payloads reach swarm workers too.

### Defensive JSON string parsing in handlers

After sanitization, array-of-object parameters arrive as
`items: {type: "string"}` with a description. The LLM may produce items
as JSON strings (`'{"caste": "coder"}'`) instead of dicts
(`{"caste": "coder"}`). The 5 affected handlers must tolerate both formats.

**Current state of each handler:**

| Handler | File:Line | Current parsing | Needs fix? |
|---------|-----------|-----------------|------------|
| `_spawn_colony` | `queen_tools.py:1935` | `_parse_caste_slots()` handles plain strings and dicts, but not JSON strings | **Yes** |
| `_spawn_parallel` | `queen_tools.py:2171` | `ColonyTask(**t)` crashes if `t` is a string | **Yes** |
| `define_workflow_steps` | `queen_thread.py:185` | `raw_steps` iterated as dicts | **Yes** |
| `propose_plan` | `queen_tools.py:3528` | each option is treated as a dict | **Yes** |
| `patch_file` | `runner.py:2051` | `operations` typed as `list[dict[str, str]]` | **Yes** |

**Apply in the 5 handlers:**

- `_parse_caste_slots()` (`queen_tools.py:146`): when `entry` is a string,
  try `json.loads(entry)` first; if that yields a dict, parse it as a slot;
  otherwise keep the current plain-caste-name behavior
- `_spawn_parallel()` (`queen_tools.py:2171`): wrap `raw_tasks` through
  `coerce_array_items()` before `ColonyTask(**t)`
- `_propose_plan()` (`queen_tools.py:3517`): wrap `options` through
  `coerce_array_items()`
- `define_workflow_steps()` (`queen_thread.py:178`): wrap `raw_steps`
  through `coerce_array_items()` before iterating
- `_handle_patch_file()` (`runner.py:2027` / `2051`): wrap `operations`
  through `coerce_array_items()`

This is small, local, and directly tied to the sanitization change.

### Gemini fix: OpenAI-compatible endpoint

In addition to sanitization, add a commented Gemini OpenAI-compatible
registry entry to `formicos.yaml` and `.env.example`.

```yaml
# Gemini via OpenAI-compatible endpoint (avoids native schema issues)
- address: "openai/gemini-2.5-pro"
  endpoint: "https://generativelanguage.googleapis.com/v1beta/openai"
  api_key_env: "GEMINI_API_KEY"
  context_window: 1000000
  supports_tools: true
  cost_per_input_token: 0.0
  cost_per_output_token: 0.0
  max_output_tokens: 65536
```

This routes Gemini through the already-proven OpenAI-compatible adapter
path without requiring a native Gemini adapter rewrite.

### Files

| File | Change |
|------|--------|
| `src/formicos/engine/schema_sanitize.py` | NEW: `sanitize_tool_schemas()`, `maybe_sanitize_tool_schemas()`, `coerce_array_items()` |
| `src/formicos/surface/runtime.py` | `maybe_sanitize_tool_schemas()` at 2 call sites + `extra_body` prefix fix |
| `src/formicos/surface/queen_tools.py` | `_parse_caste_slots()` JSON-string handling + `_spawn_parallel()` and `_propose_plan()` coercion |
| `src/formicos/surface/queen_thread.py` | `define_workflow_steps()` coercion |
| `src/formicos/engine/runner.py` | `_handle_patch_file()` coercion |
| `config/formicos.yaml` | commented Gemini OpenAI-compat entry |
| `.env.example` | document Gemini OpenAI-compat option |
| `tests/unit/engine/test_schema_sanitize.py` | NEW: sanitization + coercion tests |

### Do not touch

- `llm_gemini.py`
- `llm_openai_compatible.py`
- `llm_anthropic.py`
- `surface/queen_runtime.py`
- `docker-compose.yml` (Track 3 owns this)

### Validation

```bash
pytest tests/unit/engine/test_schema_sanitize.py -v

# Real runtime check
docker compose -f docker-compose.yml -f docker-compose.local-swarm.yml restart formicos

# Verify:
# 1. Queen (local 35B) can call spawn_colony with castes array
# 2. Colony workers (4B swarm) can call patch_file with operations array
# 3. Anthropic/OpenAI providers still receive rich schemas unchanged
# 4. Gemini via OpenAI-compat accepts all tool schemas if configured
```

---

## Track 2: Event Replay Fix

### What to build

Add `handler: str = ""` to `ServiceTriggerFired` in `core/events.py`.

```python
class ServiceTriggerFired(EventEnvelope):
    type: Literal["ServiceTriggerFired"] = "ServiceTriggerFired"
    addon_name: str = Field(..., description="Addon that owns the trigger.")
    trigger_type: str = Field(default="", description="cron | event | webhook | manual")
    handler: str = Field(default="", description="Handler reference that was invoked.")
    workspace_id: str = Field(default="")
    details: str = Field(default="", description="Human-readable trigger context.")
```

`FrozenConfig` forbids extra fields. Adding the declared field makes existing
persisted events deserialize cleanly and keeps new events backward-compatible.

### Files

| File | Change |
|------|--------|
| `src/formicos/core/events.py` | add `handler` field |

### Do not touch

- no other event types
- no event store changes
- no projection changes

### Validation

```bash
docker compose restart formicos

# Check logs for zero ServiceTriggerFired validation errors
docker logs formicos-colony 2>&1 | grep -i "ServiceTriggerFired\|validation"
```

---

## Track 3: Security Hardening

### 3A: Docker capability dropping

Add `cap_drop` to the `formicos` service in `docker-compose.yml`.

```yaml
services:
  formicos:
    cap_drop:
      - NET_RAW
      - SYS_CHROOT
      - MKNOD
      - AUDIT_WRITE
```

Keep:

- `DAC_OVERRIDE` for writes inside `/data`
- `NET_BIND_SERVICE` for binding port 8080

### 3B: Metadata endpoint validation

**`src/formicos/surface/ssrf_validate.py` (~50 lines NEW)**

Validate model endpoints at startup against metadata/special-case targets
without breaking legitimate localhost, Docker, or LAN model endpoints.

```python
import ipaddress
import socket
from urllib.parse import urlparse

_DOCKER_SERVICES = {"llm", "qdrant", "formicos-embed", "llm-swarm", "docker-proxy"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_BLOCKED_HOSTS = {"metadata.google.internal", "metadata"}
_BLOCKED_IPS = {"169.254.169.254", "169.254.170.2", "100.100.100.200"}

def validate_endpoint_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if hostname in _DOCKER_SERVICES or hostname in _LOCAL_HOSTS:
        return
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked metadata host: {hostname}")

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(resolved)
        except socket.gaierror:
            return

    if str(addr) in _BLOCKED_IPS or addr.is_link_local:
        raise ValueError(f"Blocked metadata/link-local address: {addr}")
```

**Hook in `app.py`** at adapter creation. Validate each model endpoint
before creating the adapter:

```python
from formicos.surface.ssrf_validate import validate_endpoint_url

for model in settings.models.registry:
    if model.endpoint:
        try:
            validate_endpoint_url(model.endpoint)
        except ValueError as e:
            log.warning("endpoint_blocked", endpoint=model.endpoint, error=str(e))
            continue
```

Run at startup only, not per-request.

### Files

| File | Change |
|------|--------|
| `docker-compose.yml` | `cap_drop` on `formicos` service |
| `src/formicos/surface/ssrf_validate.py` | NEW |
| `src/formicos/surface/app.py` | metadata endpoint validation at adapter creation |
| `tests/unit/surface/test_ssrf_validate.py` | NEW |

### Do not touch

- no adapter files
- no engine files
- no frontend files

### Validation

```bash
docker compose down && docker compose up -d
curl http://localhost:8080/health

pytest tests/unit/surface/test_ssrf_validate.py -v

# Verify:
# 1. localhost and Docker service endpoints still work
# 2. metadata endpoint is blocked
```

---

## Cross-track file ownership

| File | Track 1 | Track 2 | Track 3 |
|------|---------|---------|---------|
| `src/formicos/engine/schema_sanitize.py` | NEW | -- | -- |
| `src/formicos/surface/runtime.py` | sanitize + `extra_body` fix | -- | -- |
| `src/formicos/surface/queen_tools.py` | handler coercion | -- | -- |
| `src/formicos/surface/queen_thread.py` | workflow-step coercion | -- | -- |
| `src/formicos/engine/runner.py` | patch_file coercion | -- | -- |
| `src/formicos/core/events.py` | -- | handler field | -- |
| `docker-compose.yml` | -- | -- | cap_drop |
| `src/formicos/surface/ssrf_validate.py` | -- | -- | NEW |
| `src/formicos/surface/app.py` | -- | -- | endpoint validation |
| `config/formicos.yaml` | Gemini compat entry | -- | -- |
| `.env.example` | Gemini compat doc | -- | -- |

No file conflicts between tracks.

---

## What this wave does NOT do

- no llama.cpp rebuild
- no custom Jinja template extraction from GGUF
- no Gemini native adapter rewrite
- no VRAM optimization
- no credential-isolation sidecar
- no full private-network policy enforcement

---

## Success conditions

1. Queen on local Qwen3.5-35B calls `spawn_colony` with caste arrays
   without Jinja parser errors.
2. Colony workers on local Qwen3.5-4B use all colony tools including
   `patch_file` without parser errors.
3. Anthropic/OpenAI providers continue to operate on rich schemas unchanged.
4. Gemini via OpenAI-compat endpoint accepts all tool schemas when configured.
5. Event replay shows zero `ServiceTriggerFired` validation errors.
6. `docker compose up` applies `cap_drop` without breaking functionality.
7. Metadata endpoint validation blocks `http://169.254.169.254` while
   allowing localhost and Docker service names.
8. The swarm experiment (test-sentinel addon) can run end-to-end with
   local models.
9. All existing tests pass unchanged.
