"""CONFIG_UPDATE payload validator — preventive infrastructure for Wave 18.

Validates Queen-originated config mutation payloads before they reach the
config tree.  Ships as an importable, tested module in Wave 17.  The Queen
does NOT have a CONFIG_UPDATE tool yet — this is a prerequisite for adding it.

Validation pipeline (in order):
  1. Payload size cap
  2. JSON parse (if string)
  3. Recursive depth guard
  4. Forbidden string scan
  5. Forbidden config prefix deny-list
  6. Param-path whitelist check
  7. NaN/Inf rejection
  8. Type + range enforcement

Adapted from prealpha ``config_validator.py``.  Key changes:
  - Paths updated from ``recipes.*`` to ``castes.*`` (live schema)
  - Caste names updated to live set (queen, coder, reviewer, researcher, archivist)
  - ``FORBIDDEN_CONFIG_PREFIXES`` added (defense in depth)
  - ``PARAM_RULES`` built from ``config/experimentable_params.yaml``
  - Uses ``structlog`` (not ``logging``)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import structlog
from pydantic import BaseModel, Field, field_validator

log = structlog.get_logger()

# ── Security Constants ────────────────────────────────────────────────────────

MAX_PAYLOAD_DEPTH = 4
MAX_PAYLOAD_LENGTH = 2048

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

# ── Forbidden Config Prefixes (defense in depth) ─────────────────────────────
#
# Even if a path somehow passes the whitelist, it is rejected if it starts
# with any of these prefixes.  These protect security-critical config.

FORBIDDEN_CONFIG_PREFIXES: frozenset[str] = frozenset({
    "system.",           # host, port, data_dir
    "models.registry.",  # API keys, endpoints
    "embedding.",        # model swap
    "vector.",           # Qdrant URL
    "knowledge_graph.",  # DB paths
    "skill_bank.",       # confidence tuning
})

# ── Param Rules (loaded from experimentable_params.yaml) ─────────────────────

_PARAMS_PATH = Path(__file__).resolve().parents[3] / "config" / "experimentable_params.yaml"


def _load_param_rules() -> dict[str, dict[str, Any]]:
    """Build PARAM_RULES from ``config/experimentable_params.yaml``.

    Falls back to an empty dict if the file is missing (tests may run
    without the config directory).
    """
    if not _PARAMS_PATH.exists():
        return {}

    import yaml  # noqa: PLC0415 — deferred to avoid import cost when unused

    with _PARAMS_PATH.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    rules: dict[str, dict[str, Any]] = {}
    for entry in data.get("experimentable_params", []):
        entry_d: dict[str, Any] = cast("dict[str, Any]", entry) if isinstance(entry, dict) else {}
        path: str = str(entry_d.get("path", ""))
        if not path:
            continue
        rules[path] = {
            "type": str(entry_d.get("type", "float")),
            "min": entry_d.get("min", 0),
            "max": entry_d.get("max", 1),
        }
    return rules


PARAM_RULES: dict[str, dict[str, Any]] = _load_param_rules()


# ── Security Helpers ──────────────────────────────────────────────────────────


def _check_depth(obj: object, max_depth: int = MAX_PAYLOAD_DEPTH, _current: int = 0) -> bool:
    """Return True if *obj* nesting depth exceeds *max_depth*."""
    if _current > max_depth:
        return True
    if isinstance(obj, dict):
        d = cast("dict[str, Any]", obj)
        return any(_check_depth(v, max_depth, _current + 1) for v in d.values())
    if isinstance(obj, list):
        return any(_check_depth(v, max_depth, _current + 1) for v in cast("list[Any]", obj))
    return False


def _contains_forbidden(obj: object) -> str | None:
    """Return the first forbidden substring found in any string value, or None."""
    if isinstance(obj, str):
        lower = obj.lower()
        for pattern in FORBIDDEN_STRINGS:
            if pattern.lower() in lower:
                return pattern
    elif isinstance(obj, dict):
        for v in cast("dict[str, Any]", obj).values():
            hit = _contains_forbidden(v)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in cast("list[Any]", obj):
            hit = _contains_forbidden(v)
            if hit is not None:
                return hit
    return None


def _check_nan_inf(value: object) -> bool:
    """Return True if *value* is NaN or Inf (float or string representation)."""
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        return lower in ("nan", "inf", "-inf", "+inf", "infinity", "-infinity")
    return False


def _matches_forbidden_prefix(path: str) -> str | None:
    """Return the matching forbidden prefix, or None."""
    for prefix in FORBIDDEN_CONFIG_PREFIXES:
        if path.startswith(prefix):
            return prefix
    return None


# ── Pydantic Models ──────────────────────────────────────────────────────────


class ConfigUpdatePayload(BaseModel):
    """Validated CONFIG_UPDATE directive payload.

    Only ``param_path`` and ``value`` are retained; all other keys are
    silently stripped.
    """

    model_config = {"extra": "ignore"}

    param_path: str
    value: Any = Field(default=None)

    @field_validator("param_path")
    @classmethod
    def param_path_must_be_known(cls, v: str) -> str:
        if v not in PARAM_RULES:
            raise ValueError(f"unknown param_path: {v!r}")
        return v


class ConfigValidationResult(BaseModel):
    """Outcome of validating a CONFIG_UPDATE payload."""

    valid: bool = False
    param_path: str = ""
    value: Any = None
    error: str = ""


# ── Public API ───────────────────────────────────────────────────────────────


def validate_config_update(raw_payload: str | dict[str, Any]) -> ConfigValidationResult:
    """Validate a CONFIG_UPDATE directive payload.

    Parameters
    ----------
    raw_payload:
        Either a JSON string or an already-parsed dict with
        ``param_path`` and ``value`` keys.

    Returns
    -------
    ConfigValidationResult
        ``.valid`` is True when the payload is safe to apply.
    """
    # 1. Payload size cap (string only)
    if isinstance(raw_payload, str) and len(raw_payload) > MAX_PAYLOAD_LENGTH:
        return ConfigValidationResult(
            error=f"payload too large ({len(raw_payload)} chars, max {MAX_PAYLOAD_LENGTH})",
        )

    # 2. JSON parse
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError) as exc:
            return ConfigValidationResult(error=f"unparseable JSON: {exc}")
        except RecursionError:
            return ConfigValidationResult(error="payload exceeds recursion limit")

    if not isinstance(raw_payload, dict):
        return ConfigValidationResult(error="payload must be a JSON object")

    # 3. Recursive depth guard
    if _check_depth(raw_payload):
        return ConfigValidationResult(
            error=f"payload nesting exceeds max depth ({MAX_PAYLOAD_DEPTH})",
        )

    # 4. Forbidden string scan
    forbidden_hit = _contains_forbidden(raw_payload)
    if forbidden_hit is not None:
        return ConfigValidationResult(
            error=f"payload contains forbidden content: {forbidden_hit!r}",
        )

    # 5. Forbidden config prefix deny-list
    param_path = raw_payload.get("param_path", "")
    if isinstance(param_path, str):
        prefix_hit = _matches_forbidden_prefix(param_path)
        if prefix_hit is not None:
            return ConfigValidationResult(
                error=f"param_path starts with forbidden prefix: {prefix_hit!r}",
            )

    # 6. Pydantic validation (whitelist check + key stripping)
    try:
        parsed = ConfigUpdatePayload.model_validate(raw_payload)
    except Exception as exc:  # noqa: BLE001
        from pydantic import ValidationError  # noqa: PLC0415

        if isinstance(exc, ValidationError):
            errs = exc.errors()
            first_err: dict[str, Any] = dict(errs[0]) if errs else {}
            msg = str(first_err.get("msg", str(exc)))
        else:
            msg = str(exc)
        return ConfigValidationResult(error=msg)

    # 7. NaN/Inf guard
    if _check_nan_inf(parsed.value):
        return ConfigValidationResult(
            param_path=parsed.param_path,
            error="value must be finite (NaN/Inf rejected)",
        )

    # 8. Type + range enforcement
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


__all__ = ["ConfigValidationResult", "validate_config_update"]
