"""Tests for task_receipts.py — contract persistence, receipt determinism, sponsors."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from formicos.surface.task_receipts import (
    build_receipt,
    contracts_dir,
    load_contract,
    load_sponsors,
    save_contract,
    sponsors_path,
)

# Stable mock transcript for deterministic hash testing
_MOCK_TRANSCRIPT = {"final_output": "done", "rounds": [{"round": 1}]}


@pytest.fixture()
def data_dir(tmp_path):
    """Provide a data_dir whose parent has a .formicos directory."""
    d = tmp_path / "data"
    d.mkdir()
    return str(d)


# ── Contract persistence ──


class TestContractPersistence:
    def test_save_and_load_contract(self, data_dir: str) -> None:
        contract = {
            "schema": "formicos/contribution-contract",
            "version": 1,
            "sponsor": {"name": "acme"},
        }
        save_contract(data_dir, "colony-1", contract)
        loaded = load_contract(data_dir, "colony-1")
        assert loaded is not None
        assert loaded["schema"] == "formicos/contribution-contract"
        assert loaded["sponsor"]["name"] == "acme"

    def test_load_missing_contract(self, data_dir: str) -> None:
        assert load_contract(data_dir, "nonexistent") is None

    def test_contracts_dir_created(self, data_dir: str) -> None:
        d = contracts_dir(data_dir)
        assert d.exists()
        assert d.name == "contracts"

    def test_contract_is_json_file(self, data_dir: str) -> None:
        save_contract(data_dir, "col-x", {"a": 1})
        path = contracts_dir(data_dir) / "col-x.json"
        assert path.exists()
        parsed = json.loads(path.read_text())
        assert parsed["a"] == 1


# ── Sponsor verification ──


class TestSponsorVerification:
    def test_load_sponsors_empty_when_missing(self, data_dir: str) -> None:
        assert load_sponsors(data_dir) == {}

    def test_load_sponsors_from_file(self, data_dir: str) -> None:
        sp = sponsors_path(data_dir)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({
            "acme": {"verified": True, "cla_type": "corporate"},
        }))
        result = load_sponsors(data_dir)
        assert result["acme"]["verified"] is True

    def test_load_sponsors_corrupt_json(self, data_dir: str) -> None:
        sp = sponsors_path(data_dir)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text("not json")
        assert load_sponsors(data_dir) == {}


# ── Receipt building ──


def _make_colony(
    colony_id: str = "colony-1",
    status: str = "completed",
    quality_score: float = 0.85,
    cost: float = 1.23,
    round_num: int = 5,
    skills_extracted: int = 2,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    reasoning_tokens: int = 200,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=colony_id,
        status=status,
        quality_score=quality_score,
        cost=cost,
        round_number=round_num,
        skills_extracted=skills_extracted,
        budget_truth=SimpleNamespace(
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_reasoning_tokens=reasoning_tokens,
        ),
    )


def _make_runtime(
    colony: Any = None,
    data_dir: str = "/tmp/data",
) -> MagicMock:
    rt = MagicMock()
    rt.settings.system.data_dir = data_dir
    rt.projections.get_colony.return_value = colony
    return rt


@pytest.fixture(autouse=False)
def _mock_transcript():
    with patch(
        "formicos.surface.transcript.build_transcript",
        return_value=_MOCK_TRANSCRIPT,
    ):
        yield


@pytest.mark.usefixtures("_mock_transcript")
class TestBuildReceipt:
    def test_returns_none_for_missing_colony(self) -> None:
        rt = _make_runtime(colony=None)
        assert build_receipt(rt, "no-such-colony") is None

    def test_returns_none_for_running_colony(self) -> None:
        colony = _make_colony(status="running")
        rt = _make_runtime(colony=colony)
        assert build_receipt(rt, "colony-1") is None

    def test_basic_receipt_fields(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["receipt_id"] == "cr-colony-1"
        assert receipt["schema"] == "formicos/contribution-receipt"
        assert receipt["version"] == 1
        assert receipt["task_id"] == "colony-1"
        assert receipt["status"] == "completed"
        assert receipt["quality_score"] == 0.85
        assert receipt["cost"] == 1.23

    def test_token_total_includes_reasoning(self, data_dir: str) -> None:
        colony = _make_colony(
            input_tokens=1000, output_tokens=500, reasoning_tokens=200,
        )
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["total_tokens"] == 1700  # 1000 + 500 + 200

    def test_receipt_is_deterministic(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        r1 = build_receipt(rt, "colony-1")
        r2 = build_receipt(rt, "colony-1")
        assert r1 == r2

    def test_transcript_hash_stable(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        r1 = build_receipt(rt, "colony-1")
        r2 = build_receipt(rt, "colony-1")
        assert r1 is not None
        assert r2 is not None
        assert r1["transcript_hash"] == r2["transcript_hash"]
        assert len(r1["transcript_hash"]) == 64  # SHA-256 hex

    def test_unsigned_attestation(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["attestation"]["signature"] == "unsigned"

    def test_revenue_share_no_contract(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)
        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["revenue_share"]["eligible"] is False
        assert "No sponsor" in receipt["revenue_share"]["note"]

    def test_revenue_share_verified_sponsor(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)

        # Save contract with sponsor
        contract = {
            "schema": "formicos/contribution-contract",
            "version": 1,
            "contract_id": "ct-1",
            "sponsor": {"name": "acme"},
        }
        save_contract(data_dir, "colony-1", contract)

        # Save verified sponsor
        sp = sponsors_path(data_dir)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"acme": {"verified": True}}))

        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["revenue_share"]["eligible"] is True
        assert receipt["contract_id"] == "ct-1"

    def test_revenue_share_unverified_sponsor(self, data_dir: str) -> None:
        colony = _make_colony()
        rt = _make_runtime(colony=colony, data_dir=data_dir)

        contract = {
            "schema": "formicos/contribution-contract",
            "version": 1,
            "sponsor": {"name": "unknown-corp"},
        }
        save_contract(data_dir, "colony-1", contract)

        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["revenue_share"]["eligible"] is False
        assert "not verified" in receipt["revenue_share"]["note"]

    def test_failed_colony_not_eligible(self, data_dir: str) -> None:
        colony = _make_colony(status="failed")
        rt = _make_runtime(colony=colony, data_dir=data_dir)

        contract = {
            "schema": "formicos/contribution-contract",
            "version": 1,
            "sponsor": {"name": "acme"},
        }
        save_contract(data_dir, "colony-1", contract)
        sp = sponsors_path(data_dir)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"acme": {"verified": True}}))

        receipt = build_receipt(rt, "colony-1")
        assert receipt is not None
        assert receipt["revenue_share"]["eligible"] is False
        assert "failed" in receipt["revenue_share"]["note"]
