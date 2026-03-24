# ADR-030: Queen Tool Surface Expansion

**Status:** Accepted
**Date:** 2026-03-15
**Wave:** 18

## Decision

Expand the Queen's tool set from 3 to 9 tools. All new tools are read-only or proposal-only. No live config mutation in this wave.

## Context

The Queen has exactly 3 tools: `spawn_colony`, `get_status`, `kill_colony`. She cannot see templates, inspect completed colonies, read the skill bank, browse workspace files, or propose config changes. The operator gets more value from the UI than from chatting with the Queen.

Wave 17 shipped the config validator and experimentable params whitelist as preventive infrastructure. Wave 18 uses them.

## New Tools

| Tool | Type | Data source |
|------|------|-------------|
| `list_templates` | Read | `template_manager.load_templates()` |
| `inspect_template` | Read | `template_manager.load_templates()` by ID |
| `inspect_colony` | Read | `runtime.projections` |
| `list_skills` | Read | `view_state.get_skill_bank_detail()` via vector_port |
| `read_workspace_files` | Read | `os.listdir()` on workspace data dir |
| `suggest_config_change` | Propose | Two-gate validation, text-first diff |

## suggest_config_change Two-Gate Validation

Gate 1 — `config_validator.py` (structural safety):
- Forbidden strings (shell injection, XSS, code eval)
- Recursive depth guard
- NaN/Inf rejection
- Unknown param paths rejected

Gate 2 — `experimentable_params.yaml` (Queen scope):
- Only whitelisted paths are proposable
- Type and range bounds enforced
- Security-critical paths blocked regardless of whitelist

If both gates pass, the tool returns a formatted text diff. The Queen presents it to the operator. No mutation occurs.

## Consequences

- The Queen becomes meaningfully useful for operator interaction
- Template awareness prevents the Queen from hallucinating team compositions when a matching template exists
- Config proposals build operator trust before the live mutation path ships
- `_MAX_TOOL_ITERATIONS` raised from 3 to 5 to accommodate multi-tool interactions

## Rejected Alternatives

**Structured diff via new event type**
Rejected for this wave. Text-first proposals through the existing chat channel are simpler and sufficient. A richer structured diff card may come in Wave 19 when the actual mutation path is wired.

**Full CONFIG_UPDATE with live mutation**
Rejected. Proposal-only builds operator trust first. The mutation path requires additional UX (undo, confirm, persist) that belongs in a dedicated wave.

**Pre-LLM semantic template matching**
Rejected. Adding invisible pre-routing before the LLM makes Queen behavior harder to reason about. Better to teach the Queen to use `list_templates` explicitly via the system prompt.

## Implementation Note

See `docs/waves/wave_18/algorithms.md`, §1.
