"""Shared helpers for queen_runtime and queen_tools (breaks circular import)."""
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# Cache for experimentable params whitelist
_experimentable_cache: dict[str, dict[str, Any]] | None = None
_EXPERIMENTABLE_PATH = Path(__file__).resolve().parents[3] / "config" / "experimentable_params.yaml"


def _load_experimentable_params() -> dict[str, dict[str, Any]]:
    """Load and cache the experimentable params whitelist."""
    global _experimentable_cache  # noqa: PLW0603
    if _experimentable_cache is not None:
        return _experimentable_cache

    if not _EXPERIMENTABLE_PATH.exists():
        _experimentable_cache = {}
        return _experimentable_cache

    with _EXPERIMENTABLE_PATH.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}

    result: dict[str, dict[str, Any]] = {}
    for raw_entry in data.get("experimentable_params", []):
        if not isinstance(raw_entry, dict):
            continue
        entry: dict[str, Any] = raw_entry
        path = str(entry.get("path", ""))
        if path:
            result[path] = {
                "type": str(entry.get("type", "float")),
                "min": entry.get("min", 0),
                "max": entry.get("max", 1),
            }
    _experimentable_cache = result
    return _experimentable_cache


def _is_experimentable(param_path: str) -> bool:
    """Check if a param path is in the experimentable whitelist."""
    return param_path in _load_experimentable_params()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class PendingConfigProposal:
    """Thread-scoped pending config proposal awaiting operator approval."""

    proposal_id: str
    thread_id: str
    param_path: str
    proposed_value: str
    current_value: str
    reason: str
    proposed_at: datetime
    ttl_minutes: int = 30

    @property
    def is_expired(self) -> bool:
        return _now() > self.proposed_at + timedelta(minutes=self.ttl_minutes)


__all__ = ["PendingConfigProposal", "_is_experimentable", "_now"]
