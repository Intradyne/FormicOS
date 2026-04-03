"""Wave 78.5 Track 1: Provider-aware tool schema sanitization.

Flattens nested array-of-object schemas into array-of-string with
descriptive text and inline JSON example. This avoids the Jinja template
parser bug in llama.cpp when processing Qwen3.5 chat templates.

Pure dict transformation — no surface imports, no adapter imports,
no runtime state. Lives in engine/ for layer compliance.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from typing import Any


def sanitize_tool_schemas(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy and flatten nested object-in-array schemas."""
    return [_sanitize_one(copy.deepcopy(s)) for s in specs]


def maybe_sanitize_tool_schemas(
    provider: str,
    specs: Sequence[dict[str, Any]] | None,
) -> Sequence[dict[str, Any]] | None:
    """Conditionally sanitize schemas based on provider prefix.

    Only sanitizes for providers known to choke on nested schemas:
    llama-cpp, llama-cpp-swarm, gemini (native).
    """
    if not specs:
        return specs
    if provider in {"llama-cpp", "llama-cpp-swarm", "gemini"}:
        return sanitize_tool_schemas(list(specs))
    return specs


def coerce_array_items(items: list[Any]) -> list[dict[str, Any]]:
    """Coerce array items that may be JSON strings into dicts.

    After sanitization, LLMs may produce array items as JSON strings
    (e.g. ``'{"caste": "coder"}'``) instead of dicts. This tolerates both.
    """
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            try:
                parsed = json.loads(item)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                result.append(parsed)
    return result


def _sanitize_one(spec: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested array-of-object parameters in a single tool spec."""
    params = spec.get("parameters", {})
    props = params.get("properties", {})

    for _prop_name, prop_def in list(props.items()):
        if prop_def.get("type") != "array":
            continue
        items = prop_def.get("items", {})
        if items.get("type") != "object" or "properties" not in items:
            continue

        # Build descriptive text from the nested object schema
        inner_props = items["properties"]
        field_descs = []
        for fname, fdef in inner_props.items():
            ftype = fdef.get("type", "string")
            fdesc = fdef.get("description", "")
            field_descs.append(f"{fname} ({ftype}): {fdesc}" if fdesc else f"{fname} ({ftype})")

        # Build example from required fields
        required = items.get("required", list(inner_props.keys())[:3])
        example_obj: dict[str, Any] = {}
        for rfield in required:
            rdef = inner_props.get(rfield, {})
            rtype = rdef.get("type", "string")
            if rtype == "integer":
                example_obj[rfield] = 1
            elif rtype == "number":
                example_obj[rfield] = 0.0
            elif rtype == "boolean":
                example_obj[rfield] = True
            elif rtype == "array":
                example_obj[rfield] = []
            else:
                example_obj[rfield] = f"<{rfield}>"

        original_desc = prop_def.get("description", "")
        fields_text = "; ".join(field_descs)
        example_json = json.dumps(example_obj, ensure_ascii=False)

        prop_def["items"] = {"type": "string"}
        prop_def["description"] = (
            f"{original_desc} "
            f"Each item is a JSON object string with fields: {fields_text}. "
            f"Example item: {example_json}"
        ).strip()

    return spec
