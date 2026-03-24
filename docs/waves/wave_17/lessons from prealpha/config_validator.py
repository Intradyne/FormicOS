"""
FormicOS v0.12.3 -- CONFIG_UPDATE Payload Validator

Pydantic guardrails that prevent the colony_manager from crashing when
the Queen LLM hallucinates a bad CONFIG_UPDATE directive.  This runs
BEFORE the update is applied to the Context Tree overlay.

Validation rules:
  - Temperature: float, 0.0 .. 2.0
  - max_tokens:  int,   500 .. 8000
  - Unrecognized keys are stripped
  - Unknown param_paths are rejected

v0.12.3 Phase 3 — Coder 1
v0.12.3 Phase 5 — Security hardening (recursive depth guard, forbidden strings)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger("formicos.config_validator")

# ── Security Constants (v0.12.3 Phase 5) ─────────────────────────────────

MAX_PAYLOAD_DEPTH = 4       # CONFIG_UPDATE payloads should be flat dicts
MAX_PAYLOAD_LENGTH = 2048   # Reject absurdly large raw JSON strings

FORBIDDEN_STRINGS: frozenset[str] = frozenset({
    "\x00",           # null byte
    "rm -rf",         # shell injection
    "rm -r ",         # shell injection variant
    "$((", "${",      # shell expansion
    "eval(", "exec(", # code eval/exec
    "__import__",     # Python import injection
    "os.system(",     # system call
    "subprocess.",    # subprocess module
    "<script",        # XSS
    "javascript:",    # XSS via URL
})

# ── Safety bounds for CONFIG_UPDATE values ────────────────────────────────
#
# These are broader than experimentable_params.yaml (which governs EvoFlow
# mutation).  These bounds exist to prevent LLM hallucination from crashing
# the colony — not to constrain scientific experiments.

PARAM_RULES: dict[str, dict[str, Any]] = {
    # Temperature params — any caste
    "recipes.coder.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "recipes.architect.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "recipes.researcher.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "recipes.manager.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "recipes.reviewer.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    # Token limit params
    "recipes.coder.max_tokens": {"type": "int", "min": 500, "max": 8000},
    "recipes.architect.max_tokens": {"type": "int", "min": 500, "max": 8000},
    # Context window params
    "recipes.coder.context_window": {"type": "int", "min": 4096, "max": 131072},
    # Governance trigger params
    "recipes.coder.governance_triggers.stall_repeat_threshold": {
        "type": "int", "min": 2, "max": 10,
    },
    "recipes.architect.governance_triggers.similarity_threshold": {
        "type": "float", "min": 0.70, "max": 0.99,
    },
    "recipes.architect.governance_triggers.rounds_before_force_halt": {
        "type": "int", "min": 1, "max": 10,
    },
}

# Keys allowed in a CONFIG_UPDATE payload dict
_ALLOWED_PAYLOAD_KEYS = {"param_path", "value"}


# ── Security Helpers (v0.12.3 Phase 5) ───────────────────────────────────


def _check_depth(obj: object, max_depth: int = MAX_PAYLOAD_DEPTH, _current: int = 0) -> bool:
    """Return True if *obj* nesting depth exceeds *max_depth*."""
    if _current > max_depth:
        return True
    if isinstance(obj, dict):
        return any(
            _check_depth(v, max_depth, _current + 1) for v in obj.values()
        )
    if isinstance(obj, list):
        return any(
            _check_depth(v, max_depth, _current + 1) for v in obj
        )
    return False


def _contains_forbidden(obj: object) -> str | None:
    """Return the first forbidden substring found in any string value, or None."""
    if isinstance(obj, str):
        lower = obj.lower()
        for pattern in FORBIDDEN_STRINGS:
            if pattern.lower() in lower:
                return pattern
    elif isinstance(obj, dict):
        for v in obj.values():
            hit = _contains_forbidden(v)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _contains_forbidden(v)
            if hit is not None:
                return hit
    return None


def _check_nan_inf(value: object) -> bool:
    """Return True if *value* is NaN or Inf (float or string representation)."""
    if isinstance(value, float):
        import math
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        return lower in ("nan", "inf", "-inf", "+inf", "infinity", "-infinity")
    return False


# ── Pydantic model ───────────────────────────────────────────────────────


class ConfigUpdatePayload(BaseModel):
    """Validated CONFIG_UPDATE directive payload.

    Only ``param_path`` and ``value`` are retained; all other keys are
    silently stripped via ``model_config``.
    """

    param_path: str
    value: Any

    model_config = {"extra": "ignore"}

    @field_validator("param_path")
    @classmethod
    def param_path_must_be_known(cls, v: str) -> str:
        if v not in PARAM_RULES:
            raise ValueError(f"unknown param_path: {v!r}")
        return v


# ── Public API ───────────────────────────────────────────────────────────


class ConfigValidationResult(BaseModel):
    """Outcome of validating a CONFIG_UPDATE payload."""

    valid: bool = False
    param_path: str = ""
    value: Any = None
    error: str = ""


def validate_config_update(raw_payload: str | dict) -> ConfigValidationResult:
    """Validate a CONFIG_UPDATE directive payload.

    Parameters
    ----------
    raw_payload : str | dict
        Either a JSON string or an already-parsed dict with
        ``param_path`` and ``value`` keys.

    Returns
    -------
    ConfigValidationResult
        ``.valid`` is True when the payload is safe to apply.
    """
    # ── Phase 5: Raw string length guard ─────────────────────────────
    if isinstance(raw_payload, str):
        if len(raw_payload) > MAX_PAYLOAD_LENGTH:
            return ConfigValidationResult(
                error=f"payload too large ({len(raw_payload)} chars, max {MAX_PAYLOAD_LENGTH})",
            )

    # Parse JSON string if needed
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError) as exc:
            return ConfigValidationResult(error=f"unparseable JSON: {exc}")
        except RecursionError:
            return ConfigValidationResult(error="payload exceeds recursion limit")

    if not isinstance(raw_payload, dict):
        return ConfigValidationResult(error="payload must be a JSON object")

    # ── Phase 5: Recursive depth guard ────────────────────────────────
    if _check_depth(raw_payload):
        return ConfigValidationResult(
            error=f"payload nesting exceeds max depth ({MAX_PAYLOAD_DEPTH})",
        )

    # ── Phase 5: Forbidden string scan ────────────────────────────────
    forbidden_hit = _contains_forbidden(raw_payload)
    if forbidden_hit is not None:
        return ConfigValidationResult(
            error=f"payload contains forbidden content: {forbidden_hit!r}",
        )

    # Pydantic validation strips unrecognized keys
    try:
        parsed = ConfigUpdatePayload.model_validate(raw_payload)
    except ValidationError as exc:
        first_err = exc.errors()[0] if exc.errors() else {}
        msg = first_err.get("msg", str(exc))
        return ConfigValidationResult(error=msg)

    # ── Phase 5: NaN/Inf guard ────────────────────────────────────────
    if _check_nan_inf(parsed.value):
        return ConfigValidationResult(
            param_path=parsed.param_path,
            error="value must be finite (NaN/Inf rejected)",
        )

    # Type + range check against PARAM_RULES
    rule = PARAM_RULES[parsed.param_path]
    value = parsed.value

    if rule["type"] == "float":
        try:
            value = float(value)
        except (TypeError, ValueError):
            return ConfigValidationResult(
                param_path=parsed.param_path,
                error=f"value must be a float, got {type(value).__name__}",
            )
        if not (rule["min"] <= value <= rule["max"]):
            return ConfigValidationResult(
                param_path=parsed.param_path,
                error=f"value {value} out of range [{rule['min']}, {rule['max']}]",
            )
    elif rule["type"] == "int":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return ConfigValidationResult(
                param_path=parsed.param_path,
                error=f"value must be an int, got {type(value).__name__}",
            )
        if not (rule["min"] <= value <= rule["max"]):
            return ConfigValidationResult(
                param_path=parsed.param_path,
                error=f"value {value} out of range [{rule['min']}, {rule['max']}]",
            )

    return ConfigValidationResult(
        valid=True,
        param_path=parsed.param_path,
        value=value,
    )


def validate_config_update_batch(
    directives: list,
) -> tuple[list, list]:
    """Validate a batch of CONFIG_UPDATE directives.

    Parameters
    ----------
    directives : list
        List of StrategicDirective objects with ``.payload`` JSON strings.

    Returns
    -------
    (valid, rejected) : tuple[list, list]
        ``valid`` contains directives that passed validation.
        ``rejected`` contains (directive, error_message) tuples.
    """
    valid: list = []
    rejected: list[tuple] = []

    for directive in directives:
        result = validate_config_update(directive.payload)
        if result.valid:
            valid.append(directive)
        else:
            rejected.append((directive, result.error))
            logger.warning(
                "CONFIG_UPDATE directive %s rejected by validator: %s",
                getattr(directive, "directive_id", "?"),
                result.error,
            )

    return valid, rejected
