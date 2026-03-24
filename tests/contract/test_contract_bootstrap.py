"""Contract tests — verify the frozen contract files are valid and consistent."""

from __future__ import annotations

import importlib.util
import py_compile
import sys
from pathlib import Path
from typing import Literal, Union, get_args

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "docs" / "contracts"


def _load_module(name: str, path: Path):
    """Load a Python module from an arbitrary file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, f"Could not create spec for {path}"
    assert spec.loader is not None, f"No loader for {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------
# 1. events.py is importable
# ------------------------------------------------------------------


class TestContractEventsImportable:
    def test_contract_events_importable(self) -> None:
        """docs/contracts/events.py can be loaded as a module."""
        mod = _load_module("_contract_events", CONTRACTS / "events.py")
        assert hasattr(mod, "FormicOSEvent")


# ------------------------------------------------------------------
# 2. FormicOSEvent union has exactly 37 members
# ------------------------------------------------------------------


class TestEventUnionSize:
    def test_event_union_has_37_members(self) -> None:
        """The closed FormicOSEvent union contains exactly 45 types."""
        mod = _load_module("_contract_events_count", CONTRACTS / "events.py")
        event_alias = mod.FormicOSEvent

        # FormicOSEvent is Annotated[Union[...], Field(...)], so peel Annotated first
        annotated_args = get_args(event_alias)
        assert len(annotated_args) >= 1, "Expected Annotated wrapper"
        union_type = annotated_args[0]
        members = get_args(union_type)
        assert len(members) == 65, (
            f"Expected 65 event types in the union, got {len(members)}: "
            f"{[m.__name__ for m in members]}"
        )


# ------------------------------------------------------------------
# 3. ports.py compiles cleanly
# ------------------------------------------------------------------


class TestContractPortsCompiles:
    def test_contract_ports_compiles(self) -> None:
        """docs/contracts/ports.py passes py_compile without errors."""
        py_compile.compile(str(CONTRACTS / "ports.py"), doraise=True)


# ------------------------------------------------------------------
# 4. EventTypeName literals match event class names
# ------------------------------------------------------------------


class TestEventTypeNamesMatchClasses:
    def test_event_type_names_match_classes(self) -> None:
        """Every name in the EventTypeName Literal matches a class in events.py."""
        events_mod = _load_module("_contract_events_names", CONTRACTS / "events.py")
        ports_mod = _load_module("_contract_ports_names", CONTRACTS / "ports.py")

        # Extract Literal members from EventTypeName
        type_names = set(get_args(ports_mod.EventTypeName))
        assert len(type_names) == 65, (
            f"Expected 65 EventTypeName literals, got {len(type_names)}"
        )

        # Extract class names from the FormicOSEvent union
        annotated_args = get_args(events_mod.FormicOSEvent)
        union_type = annotated_args[0]
        class_names = {cls.__name__ for cls in get_args(union_type)}

        assert type_names == class_names, (
            f"Mismatch between EventTypeName and FormicOSEvent union.\n"
            f"  In EventTypeName only: {type_names - class_names}\n"
            f"  In FormicOSEvent only: {class_names - type_names}"
        )
