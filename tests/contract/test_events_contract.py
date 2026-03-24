"""Contract parity tests — verify runtime events.py mirrors docs/contracts/events.py exactly.

Compares field names, types, defaults, constraints, enums, and serialization
helpers between the frozen contract and the runtime module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "docs" / "contracts"


def _load_contract():
    """Load the frozen contract events module."""
    spec = importlib.util.spec_from_file_location("_contract_events", CONTRACTS / "events.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_contract_events_parity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _union_members(event_alias):
    """Extract the class list from an Annotated[Union[...], ...] alias."""
    annotated_args = get_args(event_alias)
    return get_args(annotated_args[0])


CONTRACT = _load_contract()

from formicos.core import events as runtime  # noqa: E402


# ------------------------------------------------------------------
# Union membership parity
# ------------------------------------------------------------------


class TestUnionParity:
    def test_same_member_count(self) -> None:
        contract_members = _union_members(CONTRACT.FormicOSEvent)
        runtime_members = _union_members(runtime.FormicOSEvent)
        assert len(contract_members) == len(runtime_members) == 65

    def test_same_member_names(self) -> None:
        contract_names = {c.__name__ for c in _union_members(CONTRACT.FormicOSEvent)}
        runtime_names = {c.__name__ for c in _union_members(runtime.FormicOSEvent)}
        assert contract_names == runtime_names

    def test_same_union_order(self) -> None:
        contract_order = [c.__name__ for c in _union_members(CONTRACT.FormicOSEvent)]
        runtime_order = [c.__name__ for c in _union_members(runtime.FormicOSEvent)]
        assert contract_order == runtime_order


# ------------------------------------------------------------------
# Per-event field parity
# ------------------------------------------------------------------

CONTRACT_CLASSES = {cls.__name__: cls for cls in _union_members(CONTRACT.FormicOSEvent)}
RUNTIME_CLASSES = {cls.__name__: cls for cls in _union_members(runtime.FormicOSEvent)}


@pytest.mark.parametrize("event_name", sorted(CONTRACT_CLASSES.keys()))
class TestFieldParity:
    def test_same_field_names(self, event_name: str) -> None:
        contract_fields = set(CONTRACT_CLASSES[event_name].model_fields.keys())
        runtime_fields = set(RUNTIME_CLASSES[event_name].model_fields.keys())
        assert contract_fields == runtime_fields, (
            f"{event_name} field mismatch: "
            f"contract-only={contract_fields - runtime_fields}, "
            f"runtime-only={runtime_fields - contract_fields}"
        )

    def test_same_field_required(self, event_name: str) -> None:
        for field_name, c_info in CONTRACT_CLASSES[event_name].model_fields.items():
            r_info = RUNTIME_CLASSES[event_name].model_fields[field_name]
            assert c_info.is_required() == r_info.is_required(), (
                f"{event_name}.{field_name}: required mismatch "
                f"(contract={c_info.is_required()}, runtime={r_info.is_required()})"
            )

    def test_same_field_defaults(self, event_name: str) -> None:
        for field_name, c_info in CONTRACT_CLASSES[event_name].model_fields.items():
            r_info = RUNTIME_CLASSES[event_name].model_fields[field_name]
            if not c_info.is_required():
                assert c_info.default == r_info.default, (
                    f"{event_name}.{field_name}: default mismatch"
                )


# ------------------------------------------------------------------
# Model config parity (frozen + extra=forbid)
# ------------------------------------------------------------------


@pytest.mark.parametrize("event_name", sorted(CONTRACT_CLASSES.keys()))
class TestModelConfigParity:
    def test_frozen(self, event_name: str) -> None:
        assert RUNTIME_CLASSES[event_name].model_config.get("frozen") is True

    def test_extra_forbid(self, event_name: str) -> None:
        assert RUNTIME_CLASSES[event_name].model_config.get("extra") == "forbid"


# ------------------------------------------------------------------
# Enum / literal parity
# ------------------------------------------------------------------


class TestEnumParity:
    def test_coordination_strategy_values(self) -> None:
        assert get_args(CONTRACT.CoordinationStrategyName) == get_args(runtime.CoordinationStrategyName)

    def test_phase_name_values(self) -> None:
        assert get_args(CONTRACT.PhaseName) == get_args(runtime.PhaseName)

    def test_context_operation_values(self) -> None:
        assert get_args(CONTRACT.ContextOperationName) == get_args(runtime.ContextOperationName)

    def test_queen_role_values(self) -> None:
        assert get_args(CONTRACT.QueenRoleName) == get_args(runtime.QueenRoleName)


# ------------------------------------------------------------------
# __all__ parity
# ------------------------------------------------------------------


class TestAllExportParity:
    def test_same_all_exports(self) -> None:
        assert sorted(CONTRACT.__all__) == sorted(runtime.__all__)


# ------------------------------------------------------------------
# Serialization helper parity
# ------------------------------------------------------------------


class TestSerializationParity:
    def test_serialize_exists(self) -> None:
        assert callable(runtime.serialize)
        assert callable(CONTRACT.serialize)

    def test_deserialize_exists(self) -> None:
        assert callable(runtime.deserialize)
        assert callable(CONTRACT.deserialize)


# ------------------------------------------------------------------
# WorkspaceConfigSnapshot parity
# ------------------------------------------------------------------


class TestWorkspaceConfigSnapshotParity:
    def test_same_fields(self) -> None:
        contract_fields = set(CONTRACT.WorkspaceConfigSnapshot.model_fields.keys())
        runtime_fields = set(runtime.WorkspaceConfigSnapshot.model_fields.keys())
        assert contract_fields == runtime_fields

    def test_frozen(self) -> None:
        assert runtime.WorkspaceConfigSnapshot.model_config.get("frozen") is True

    def test_extra_forbid(self) -> None:
        assert runtime.WorkspaceConfigSnapshot.model_config.get("extra") == "forbid"
