"""Contract sync tests — verify Python events align with docs/contracts/types.ts.

Parses the TypeScript contract file and checks that:
- EventTypeName union has the same 27 members
- Each TS event interface has fields matching the Python model (after camelCase transform)
- BaseEvent envelope fields match EventEnvelope
- FormicOSEvent TS union has the same 27 members in the same order
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from formicos.core.events import FormicOSEvent

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_CONTRACT = REPO_ROOT / "docs" / "contracts" / "types.ts"

# Read TS source once
_TS_SOURCE = TS_CONTRACT.read_text(encoding="utf-8")


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _extract_ts_event_type_names() -> list[str]:
    """Extract all string literal members from the EventTypeName union in TS."""
    pattern = r'export\s+type\s+EventTypeName\s*=\s*([\s\S]*?);'
    match = re.search(pattern, _TS_SOURCE)
    assert match, "Could not find EventTypeName in types.ts"
    block = match.group(1)
    return re.findall(r'"(\w+)"', block)


def _extract_ts_formicos_event_union() -> list[str]:
    """Extract member type names from the FormicOSEvent union in TS."""
    pattern = r'export\s+type\s+FormicOSEvent\s*=\s*([\s\S]*?);'
    match = re.search(pattern, _TS_SOURCE)
    assert match, "Could not find FormicOSEvent union in types.ts"
    block = match.group(1)
    return re.findall(r'\b(\w+Event)\b', block)


def _extract_ts_interface_fields(interface_name: str) -> dict[str, str]:
    """Extract field names and types from a TS interface."""
    pattern = rf'export\s+interface\s+{re.escape(interface_name)}\s+extends\s+\w+\s*\{{([\s\S]*?)\}}'
    match = re.search(pattern, _TS_SOURCE)
    if not match:
        return {}
    body = match.group(1)
    fields = {}
    for line in body.strip().split("\n"):
        line = line.strip().rstrip(";")
        if not line or line.startswith("//"):
            continue
        field_match = re.match(r'(\w+)(\?)?:\s*(.+)', line)
        if field_match:
            fields[field_match.group(1)] = field_match.group(3).strip()
    return fields


def _extract_ts_base_event_fields() -> dict[str, str]:
    """Extract fields from the BaseEvent interface."""
    pattern = r'export\s+interface\s+BaseEvent\s*\{([\s\S]*?)\}'
    match = re.search(pattern, _TS_SOURCE)
    assert match, "Could not find BaseEvent in types.ts"
    body = match.group(1)
    fields = {}
    for line in body.strip().split("\n"):
        line = line.strip().rstrip(";")
        if not line or line.startswith("//"):
            continue
        field_match = re.match(r'(\w+)(\?)?:\s*(.+)', line)
        if field_match:
            fields[field_match.group(1)] = field_match.group(3).strip()
    return fields


# Pre-compute Python event class map
_PY_UNION_MEMBERS = get_args(get_args(FormicOSEvent)[0])
_PY_CLASSES = {cls.__name__: cls for cls in _PY_UNION_MEMBERS}
_PY_EVENT_NAMES = [cls.__name__ for cls in _PY_UNION_MEMBERS]

# Envelope fields present in BaseEvent (shared, not repeated in each TS interface)
# Note: 'type' is NOT in TS BaseEvent — it's declared per-event interface.
_ENVELOPE_FIELDS = {"seq", "timestamp", "address", "trace_id"}
# Full set including type for per-event checks
_ALL_ENVELOPE_FIELDS = {"seq", "type", "timestamp", "address", "trace_id"}


# ------------------------------------------------------------------
# EventTypeName union parity
# ------------------------------------------------------------------


class TestEventTypeNameParity:
    def test_ts_has_37_event_type_names(self) -> None:
        ts_names = _extract_ts_event_type_names()
        assert len(ts_names) == 69

    def test_same_event_type_names(self) -> None:
        ts_names = set(_extract_ts_event_type_names())
        py_names = set(_PY_CLASSES.keys())
        assert ts_names == py_names, (
            f"TS-only: {ts_names - py_names}, PY-only: {py_names - ts_names}"
        )


# ------------------------------------------------------------------
# FormicOSEvent union parity
# ------------------------------------------------------------------


class TestFormicOSEventUnionParity:
    def test_ts_union_has_37_members(self) -> None:
        ts_members = _extract_ts_formicos_event_union()
        assert len(ts_members) == 69

    def test_ts_union_order_matches_python(self) -> None:
        ts_members = _extract_ts_formicos_event_union()
        # TS uses "WorkspaceCreatedEvent" style, Python uses "WorkspaceCreated"
        ts_base_names = [m.replace("Event", "") for m in ts_members]
        assert ts_base_names == _PY_EVENT_NAMES


# ------------------------------------------------------------------
# BaseEvent ↔ EventEnvelope field parity
# ------------------------------------------------------------------


class TestBaseEventParity:
    def test_base_event_fields_match_envelope(self) -> None:
        ts_fields = set(_extract_ts_base_event_fields().keys())
        expected_camel = {_snake_to_camel(f) for f in _ENVELOPE_FIELDS}
        assert ts_fields == expected_camel, (
            f"TS-only: {ts_fields - expected_camel}, "
            f"PY-only: {expected_camel - ts_fields}"
        )


# ------------------------------------------------------------------
# Per-event interface field parity
# ------------------------------------------------------------------

# Build list of (event_name, ts_interface_name) pairs
_EVENT_PAIRS = [(name, f"{name}Event") for name in _PY_EVENT_NAMES]


@pytest.mark.parametrize("py_name,ts_name", _EVENT_PAIRS, ids=[p[0] for p in _EVENT_PAIRS])
class TestPerEventFieldParity:
    def test_ts_fields_match_python(self, py_name: str, ts_name: str) -> None:
        ts_fields = _extract_ts_interface_fields(ts_name)
        py_cls = _PY_CLASSES[py_name]

        # Get Python non-envelope fields (envelope fields come from BaseEvent)
        py_own_fields = {
            k for k in py_cls.model_fields
            if k not in _ALL_ENVELOPE_FIELDS
        }
        py_camel = {_snake_to_camel(f) for f in py_own_fields}

        # TS interface fields (excluding 'type' which is the discriminant in BaseEvent)
        ts_field_names = {k for k in ts_fields if k != "type"} if "type" in ts_fields else set(ts_fields.keys())
        # 'type' is declared in each TS event interface too, so include it in py side
        if "type" in ts_fields:
            ts_field_names.add("type")
            py_camel.add("type")

        assert ts_field_names == py_camel, (
            f"{py_name}: TS-only={ts_field_names - py_camel}, "
            f"PY-only={py_camel - ts_field_names}"
        )
