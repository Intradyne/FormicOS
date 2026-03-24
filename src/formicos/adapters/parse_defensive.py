"""Defensive 3-stage tool-call parser shared by all LLM adapters.

Stage 1: json.loads() — fast path for clean JSON
Stage 2: json_repair.loads() — trailing commas, missing quotes, truncation
Stage 3: Regex extraction — <think> tags, markdown fences, bare JSON objects

Fuzzy-matches hallucinated tool names against known tools via difflib.
Lives in adapters/ (imports only core/).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any

import json_repair
import structlog

logger = structlog.get_logger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_BRACE_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass(frozen=True)
class ParsedToolCall:
    """Normalized tool call extracted from LLM output."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]


def parse_tool_calls_defensive(
    text: str,
    known_tools: set[str] | None = None,
) -> list[ParsedToolCall]:
    """Parse tool calls with 3-stage fallback. Returns empty list on total failure."""
    if not text or not text.strip():
        return []

    # Stage 1: native json.loads
    result = _try_json_loads(text, known_tools)
    if result is not None:
        logger.debug("parse_defensive.stage1_success", count=len(result))
        return result

    # Stage 2: json_repair
    result = _try_json_repair(text, known_tools)
    if result is not None:
        logger.debug("parse_defensive.stage2_success", count=len(result))
        return result

    # Stage 3: regex extraction after stripping <think> tags
    cleaned = _THINK_RE.sub("", text).strip()
    for pattern in [_FENCE_RE, _BRACE_RE]:
        for match in pattern.finditer(cleaned):
            candidate = match.group(1) if pattern is _FENCE_RE else match.group(0)
            candidate = candidate.strip()
            if not candidate:
                continue
            result = _try_json_repair(candidate, known_tools)
            if result is not None:
                logger.debug("parse_defensive.stage3_success", count=len(result))
                return result

    logger.debug("parse_defensive.all_stages_failed", text_len=len(text))
    return []


def _try_json_loads(
    text: str, known_tools: set[str] | None,
) -> list[ParsedToolCall] | None:
    try:
        obj = json.loads(text)
        return _extract(obj, known_tools)
    except (json.JSONDecodeError, TypeError):
        return None


def _try_json_repair(
    text: str, known_tools: set[str] | None,
) -> list[ParsedToolCall] | None:
    try:
        obj = json_repair.loads(text)  # pyright: ignore[reportUnknownMemberAccess]
        return _extract(obj, known_tools)
    except Exception:  # noqa: BLE001
        return None


def _parse_string_args(args_str: str) -> dict[str, Any]:
    """Parse args that arrived as a JSON string instead of an object."""
    try:
        parsed = json.loads(args_str)
        if isinstance(parsed, dict):
            return parsed  # type: ignore[return-value]
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        parsed = json_repair.loads(args_str)  # pyright: ignore[reportUnknownMemberAccess]
        if isinstance(parsed, dict):
            return parsed  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        pass
    return {"_raw": args_str}


def _extract(  # noqa: C901
    obj: Any,  # noqa: ANN401
    known_tools: set[str] | None,
) -> list[ParsedToolCall] | None:
    """Normalize diverse JSON shapes into ParsedToolCall list.

    Handles: {name, arguments}, {function_call: ...}, [{...}],
    {tool_calls: [...]}, {function: {name, arguments}}.
    """
    candidates: list[Any] = []

    if isinstance(obj, list):
        candidates = list(obj)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(obj, dict):
        if "name" in obj:
            candidates = [obj]
        for key in ("tool_calls", "function_calls", "calls"):
            val = obj.get(key)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            if isinstance(val, list):
                candidates.extend(val)  # pyright: ignore[reportUnknownArgumentType]
        fc = obj.get("function_call")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if isinstance(fc, dict):
            candidates.append(fc)
    else:
        return None

    calls: list[ParsedToolCall] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        name: str | None = None
        raw_name = item.get("name")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if isinstance(raw_name, str):
            name = raw_name
        else:
            func = item.get("function")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            if isinstance(func, dict):
                fn = func.get("name")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                if isinstance(fn, str):
                    name = fn

        if not name:
            continue

        args: Any = None
        for arg_key in ("arguments", "args", "input", "parameters"):
            if arg_key in item:
                args = item[arg_key]  # pyright: ignore[reportUnknownVariableType]
                break
        if args is None:
            func = item.get("function")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            if isinstance(func, dict):
                args = func.get("arguments")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if args is None:
            args = {}

        if isinstance(args, str):
            args = _parse_string_args(args)
        elif not isinstance(args, dict):
            args = {"_raw": args}  # pyright: ignore[reportUnknownArgumentType,reportUnknownVariableType]

        # Fuzzy-match against known tools
        if known_tools is not None and name not in known_tools:
            matches = get_close_matches(name, list(known_tools), n=1, cutoff=0.6)
            if matches:
                logger.debug(
                    "parse_defensive.fuzzy_match",
                    original=name, matched=matches[0],
                )
                name = matches[0]
            else:
                logger.debug("parse_defensive.unknown_tool", name=name)
                continue

        calls.append(ParsedToolCall(name=name, arguments=args))  # pyright: ignore[reportUnknownArgumentType]

    return calls if calls else None


__all__ = ["ParsedToolCall", "parse_tool_calls_defensive"]
