"""Task contract and receipt helpers for A2A economic protocol (Wave 75).

File-backed contracts and deterministic receipts. No new events.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime


def contracts_dir(data_dir: str) -> Path:
    """Return the contracts directory, creating it if needed."""
    d = Path(data_dir) / ".formicos" / "contracts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def contract_path(data_dir: str, colony_id: str) -> Path:
    """Return the path for a specific colony's contract."""
    return contracts_dir(data_dir) / f"{colony_id}.json"


def save_contract(
    data_dir: str, colony_id: str, contract: dict[str, Any],
) -> None:
    """Persist a contract to disk."""
    path = contract_path(data_dir, colony_id)
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")


def load_contract(data_dir: str, colony_id: str) -> dict[str, Any] | None:
    """Load a stored contract, or None if absent."""
    path = contract_path(data_dir, colony_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def sponsors_path(data_dir: str) -> Path:
    """Return the path to the sponsors registry."""
    return Path(data_dir) / ".formicos" / "sponsors.json"


def load_sponsors(data_dir: str) -> dict[str, Any]:
    """Load the manual sponsor registry."""
    path = sponsors_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {}


def _transcript_hash(transcript: dict[str, Any]) -> str:
    """Deterministic SHA-256 of the canonical transcript JSON."""
    canonical = json.dumps(transcript, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_receipt(
    runtime: Runtime, colony_id: str,
) -> dict[str, Any] | None:
    """Build a deterministic receipt for a terminal colony.

    Returns None if the colony doesn't exist or isn't terminal.
    """
    from formicos.surface.transcript import build_transcript  # noqa: PLC0415

    projections = getattr(runtime, "projections", None)
    if projections is None:
        return None
    colony = projections.get_colony(colony_id)
    if colony is None:
        return None
    if colony.status in ("pending", "running"):
        return None

    settings = getattr(runtime, "settings", None)
    if settings is None:
        return None
    data_dir = settings.system.data_dir
    contract = load_contract(data_dir, colony_id)
    transcript = build_transcript(colony)

    # Correct token total: input + output + reasoning (not BudgetSnapshot.total_tokens)
    bt = colony.budget_truth
    total_tokens = (
        bt.total_input_tokens + bt.total_output_tokens + bt.total_reasoning_tokens
    )

    receipt_id = f"cr-{colony_id}"
    transcript_digest = _transcript_hash(transcript)

    # Sponsor eligibility
    sponsor_name = (
        contract.get("sponsor", {}).get("name", "")
        if contract
        else ""
    )
    sponsors = load_sponsors(data_dir)
    sponsor_info = sponsors.get(sponsor_name, {}) if sponsor_name else {}
    sponsor_verified = bool(
        sponsor_info.get("verified", False) if isinstance(sponsor_info, dict) else False
    )

    eligible = sponsor_verified and colony.status == "completed"
    eligibility_note = ""
    if not sponsor_name:
        eligibility_note = "No sponsor specified in contract."
    elif not sponsor_verified:
        eligibility_note = f"Sponsor '{sponsor_name}' is not verified."
    elif colony.status != "completed":
        eligibility_note = f"Colony status is '{colony.status}', not 'completed'."

    receipt: dict[str, Any] = {
        "receipt_id": receipt_id,
        "schema": "formicos/contribution-receipt",
        "version": 1,
        "task_id": colony_id,
        "status": colony.status,
        "quality_score": colony.quality_score,
        "cost": colony.cost,
        "total_tokens": total_tokens,
        "rounds_completed": colony.round_number,
        "skills_extracted": colony.skills_extracted,
        "transcript_hash": transcript_digest,
        "attestation": {"signature": "unsigned"},
        "revenue_share": {
            "eligible": eligible,
            "note": eligibility_note,
        },
    }

    if contract:
        receipt["contract_id"] = contract.get("contract_id", receipt_id)
        receipt["contract_schema"] = contract.get("schema", "")

    return receipt
