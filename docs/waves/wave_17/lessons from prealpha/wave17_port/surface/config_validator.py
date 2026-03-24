"""
FormicOS Alpha — CONFIG_UPDATE Payload Validator

Ported from pre-alpha v0.12.3 (src/config_validator.py, 294 LOC).
Adapted for the alpha's hexagonal architecture (surface layer).

Prevents colony_manager crashes when the Queen LLM hallucinates bad
CONFIG_UPDATE directives. Runs BEFORE the update is applied to the
Context Tree overlay.

Validation layers:
  1. Payload length guard (max 2048 chars)
  2. Recursive depth guard (max 4 levels)
  3. Forbidden string scan (shell injection, code eval, XSS)
  4. NaN/Inf rejection
  5. Param path whitelist (only known paths accepted)
  6. Type + range enforcement per path
  7. Forbidden config path deny-list (security-critical paths)

Integration point: call validate_config_update() in colony_manager.py
before applying any CONFIG_UPDATE to the context tree.

Layer: surface/ (imports nothing from engine/ or adapters/).
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from pydantic import BaseModel, Field, field_validator, ValidationError

log = logging.getLogger("formicos.surface.config_validator")

# ── Security Constants ───────────────────────────────────────────────────

MAX_PAYLOAD_DEPTH = 4
MAX_PAYLOAD_LENGTH = 2048

FORBIDDEN_STRINGS: frozenset[str] = frozenset({
    "\x00",
    "rm -rf", "rm -r ",
    "$((", "${",
    "eval(", "exec(",
    "__import__",
    "os.system(",
    "subprocess.",
    "<script",
    "javascript:",
})

# Security-critical paths the Queen can NEVER mutate.
# Ported from pre-alpha research/quality_gate.py FORBIDDEN_CONFIG_PATHS.
FORBIDDEN_CONFIG_PREFIXES: tuple[str, ...] = (
    "auth.", "api_keys.", "signing_secret", "webhook_secret",
    "security.", "tls.", "ssl.", "cors.",
    "server.port", "server.host", "server.bind", "server.workers",
    "listen_port", "listen_host",
    "mcp_servers.", "mcp_gateway.", "mcp.servers.", "mcp.gateway.",
    "qdrant.", "database.", "db.", "vector_store.",
    "workspace_root", "storage.", "filesystem.",
)

# ── Param rules (adapt paths to match alpha's caste_recipes.yaml) ────────
#
# These are broader than experimentable_params.yaml (which governs EvoFlow
# mutation). These bounds prevent LLM hallucination from crashing the colony.

PARAM_RULES: dict[str, dict[str, Any]] = {
    # Temperature params — per caste
    "castes.coder.temperature":      {"type": "float", "min": 0.0, "max": 2.0},
    "castes.reviewer.temperature":   {"type": "float", "min": 0.0, "max": 2.0},
    "castes.researcher.temperature": {"type": "float", "min": 0.0, "max": 2.0},
    "castes.manager.temperature":    {"type": "float", "min": 0.0, "max": 2.0},
    "castes.archivist.temperature":  {"type": "float", "min": 0.0, "max": 2.0},
    "castes.queen.temperature":      {"type": "float", "min": 0.0, "max": 2.0},
    # Token limit params
    "castes.coder.max_tokens":       {"type": "int", "min": 500, "max": 16000},
    "castes.reviewer.max_tokens":    {"type": "int", "min": 500, "max": 8000},
    "castes.researcher.max_tokens":  {"type": "int", "min": 500, "max": 8000},
    "castes.archivist.max_tokens":   {"type": "int", "min": 500, "max": 4000},
    # Iteration caps
    "castes.coder.max_iterations":       {"type": "int", "min": 3, "max": 50},
    "castes.reviewer.max_iterations":    {"type": "int", "min": 2, "max": 15},
    "castes.researcher.max_iterations":  {"type": "int", "min": 3, "max": 50},
    # Governance triggers
    "governance.max_rounds":             {"type": "int", "min": 2, "max": 30},
    "governance.budget_usd":             {"type": "float", "min": 0.10, "max": 50.0},
}


# ── Security Helpers ─────────────────────────────────────────────────────

def _check_depth(obj: object, max_depth: int = MAX_PAYLOAD_DEPTH, _current: int = 0) -> bool:
    """Return True if nesting depth exceeds max_depth."""
    if _current > max_depth:
        return True
    if isinstance(obj, dict):
        return any(_check_depth(v, max_depth, _current + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_check_depth(v, max_depth, _current + 1) for v in obj)
    return False


def _contains_forbidden(obj: object) -> str | None:
    """Return first forbidden substring found, or None."""
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
    """Return True if value is NaN or Inf."""
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        return lower in ("nan", "inf", "-inf", "+inf", "infinity", "-infinity")
    return False


def _is_forbidden_path(param_path: str) -> bool:
    """Return True if param_path targets a security-critical config path."""
    lower = param_path.lower()
    return any(lower.startswith(prefix) for prefix in FORBIDDEN_CONFIG_PREFIXES)


# ── Pydantic model ───────────────────────────────────────────────────────

class ConfigUpdatePayload(BaseModel):
    """Validated CONFIG_UPDATE directive payload."""
    param_path: str
    value: Any
    model_config = {"extra": "ignore"}

    @field_validator("param_path")
    @classmethod
    def param_path_must_be_known(cls, v: str) -> str:
        if v not in PARAM_RULES:
            raise ValueError(f"unknown param_path: {v!r}")
        return v


# ── Result type ──────────────────────────────────────────────────────────

class ConfigValidationResult(BaseModel):
    """Outcome of validating a CONFIG_UPDATE payload."""
    valid: bool = False
    param_path: str = ""
    value: Any = None
    error: str = ""


# ── Public API ───────────────────────────────────────────────────────────

def validate_config_update(raw_payload: str | dict) -> ConfigValidationResult:
    """Validate a CONFIG_UPDATE directive payload.

    Call this in colony_manager.py before applying any CONFIG_UPDATE
    to the context tree. Returns .valid=True only when safe to apply.
    """
    # Length guard
    if isinstance(raw_payload, str):
        if len(raw_payload) > MAX_PAYLOAD_LENGTH:
            return ConfigValidationResult(
                error=f"payload too large ({len(raw_payload)} chars, max {MAX_PAYLOAD_LENGTH})",
            )

    # Parse JSON
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError) as exc:
            return ConfigValidationResult(error=f"unparseable JSON: {exc}")
        except RecursionError:
            return ConfigValidationResult(error="payload exceeds recursion limit")

    if not isinstance(raw_payload, dict):
        return ConfigValidationResult(error="payload must be a JSON object")

    # Depth guard
    if _check_depth(raw_payload):
        return ConfigValidationResult(
            error=f"payload nesting exceeds max depth ({MAX_PAYLOAD_DEPTH})",
        )

    # Forbidden string scan
    forbidden_hit = _contains_forbidden(raw_payload)
    if forbidden_hit is not None:
        return ConfigValidationResult(
            error=f"payload contains forbidden content: {forbidden_hit!r}",
        )

    # Pydantic validation
    try:
        parsed = ConfigUpdatePayload.model_validate(raw_payload)
    except ValidationError as exc:
        first_err = exc.errors()[0] if exc.errors() else {}
        msg = first_err.get("msg", str(exc))
        return ConfigValidationResult(error=msg)

    # Forbidden path check
    if _is_forbidden_path(parsed.param_path):
        return ConfigValidationResult(
            param_path=parsed.param_path,
            error=f"param_path targets security-critical config: {parsed.param_path!r}",
        )

    # NaN/Inf guard
    if _check_nan_inf(parsed.value):
        return ConfigValidationResult(
            param_path=parsed.param_path,
            error="value must be finite (NaN/Inf rejected)",
        )

    # Type + range check
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
