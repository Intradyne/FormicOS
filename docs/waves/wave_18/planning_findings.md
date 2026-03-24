# Wave 18 Planning Findings — Queen Usefulness + Runtime Completion

**Date:** 2026-03-15
**Scope:** Catch-up audit after Wave 17 A/B/C acceptance

---

## 1. The Queen Is Still Missing Basic Product Capabilities

The live Queen tool surface in `src/formicos/surface/queen_runtime.py` is still only:

- `spawn_colony`
- `get_status`
- `kill_colony`

That means the Queen still cannot directly:

- inspect colony templates
- inspect a completed colony in a structured way
- inspect the skill bank
- browse workspace files
- propose configuration changes through a guarded path

This is the main product gap. The UI is still more capable than the Queen.

---

## 2. Wave 17 Created the Right Guardrails for Proposal-Only Config Changes

Wave 17 shipped two distinct guardrails:

- `config_validator.py` for structural and security validation
- `config/experimentable_params.yaml` for scope and bounded experimentation

These should not be collapsed into one concept.

The right Wave 18 shape is:

1. validate with `config_validator.py`
2. constrain with `experimentable_params.yaml`
3. surface a text-first proposal to the operator
4. do not apply the mutation in this wave

This keeps Wave 18 in the trust-building stage rather than opening autonomous config mutation too early.

---

## 3. The Approval Surface Can Support Text-First Proposals Without New Events

The existing approval machinery is intentionally simple:

- `ApprovalRequested` carries `approval_type` and `detail`
- the frontend queue renders a compact text-first card

This is enough for Wave 18 if config proposals remain text-first and human-readable.

It is not yet a rich structured diff protocol. If Wave 19 wants field-by-field config diff rendering, that may justify a small contract extension later. Wave 18 does not need that.

---

## 4. Hidden Pre-LLM Template Matching Is Not the Right First Step

The better Wave 18 move is explicit tool use, not a hidden semantic pre-router.

Why:

- it keeps Queen behavior explainable
- it avoids adding an invisible decision layer before the LLM runs
- the tool path is already repo-native and operator-visible

Implication: teach the Queen to use `list_templates` and `inspect_template` in-band rather than pre-matching outside the model loop.

---

## 5. The Local Runtime Story Is Still Incomplete

Wave 17 improved the compose and telemetry truth, but the live default stack is still not the same as the operator’s known-good anyloom setup.

Current live repo state:

- `docker-compose.yml` defaults to `ghcr.io/ggml-org/llama.cpp:server-cuda`
- `docker-compose.yml` defaults to `LLM_CONTEXT_SIZE=32768`
- `config/formicos.yaml` sets `llama-cpp/gpt-4` `context_window: 32768`
- accepted Wave 17 smoke observed runtime-effective context of `16384`

The anyloom reference shows the stronger target:

- `local/llama.cpp:server-cuda-blackwell`
- `LLM_CONTEXT_SIZE=131072`
- same llama.cpp runtime flags otherwise

The practical conclusion is:

- Wave 18 should complete the Blackwell/high-context path
- the open question is build-path portability inside this repo, not whether the target context is desirable

---

## 6. One Concrete Gap: The Blackwell Build Script Is Referenced But Not Present

The wave materials and prealpha reference mention `scripts/build_llm_image.sh`, but that script is not currently present in this repo’s `scripts/` directory.

That means Wave 18 Track C should explicitly include:

- adding or porting the build script into this repo
- documenting the first-run build step in `.env.example` and `docs/LOCAL_FIRST_QUICKSTART.md`

This is a tooling/documentation gap, not a reason to avoid the Blackwell target.

---

## 7. The Queen Still Has a Policy Alignment Gap

Wave 16 moved model output-token policy into the model registry, but `queen_runtime.py` still derives Queen `max_tokens` from the caste recipe path.

Wave 18 should at least:

- keep the Queen from exceeding the selected model’s `max_output_tokens`
- avoid letting the Queen feel artificially constrained relative to the selected model

This is more basic than advanced autonomy and belongs in the same wave as Queen usefulness.

---

## 8. Opus Is a Real Fleet Gap, Not a Speculative Nice-To-Have

The live registry in `config/formicos.yaml` includes:

- `anthropic/claude-sonnet-4.6`
- `anthropic/claude-haiku-4.5`
- `gemini/gemini-2.5-flash`
- `gemini/gemini-2.5-flash-lite`

`anthropic/claude-opus-4.6` is not currently selectable.

Adding it in Wave 18 is reasonable because:

- it is a straightforward model-registry/product-surface addition
- it gives the operator a genuine “maximum reasoning” option for Queen-heavy workflows
- it does not require a new architecture

---

## 9. Recommended Wave 18 Shape

Wave 18 should likely be some blend of:

- Queen basics / Queen usefulness
- final operator UX hardening
- completion of the local high-context runtime story

In practice:

- Track A: Queen read/propose tools
- Track B: Queen response quality + model fleet
- Track C: Blackwell image + 131k context completion

---

## 10. Explicit Deferrals Still Make Sense

Still not good Wave 18 material:

- live CONFIG_UPDATE mutation
- experiment engine / self-evolution
- multi-colony coordination directives
- new protocol implementations
- event-union expansion for speculative future state

Wave 18 should make the Queen more capable and more trustworthy before it makes her more autonomous.
