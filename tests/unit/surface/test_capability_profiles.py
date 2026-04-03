"""Capability profile tests — shipped priors + replay overlays (Wave 82)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from formicos.surface.capability_profiles import (
    _classify_granularity,
    _dominant_worker_model,
    _resolve_profile,
    clear_cache,
    derive_overlays_from_projections,
    get_capability_evidence,
    summarize_capability,
)


def setup_function() -> None:
    clear_cache()


# ---------------------------------------------------------------------------
# summarize_capability (backward compat)
# ---------------------------------------------------------------------------


def test_exact_address_match() -> None:
    summary = summarize_capability("llama-cpp-swarm/qwen3.5-4b-swarm")
    assert summary is not None
    assert "qwen3.5-4b" in summary
    assert "files optimal" in summary


def test_short_alias_match() -> None:
    summary = summarize_capability("qwen3.5-4b-swarm")
    assert summary is not None
    assert "qwen3.5-4b" in summary


def test_suffix_normalization() -> None:
    summary = summarize_capability("qwen3.5-4b-swarm")
    assert summary is not None
    assert "0.738" in summary


def test_full_35b_profile() -> None:
    summary = summarize_capability("llama-cpp/qwen3.5-35b")
    assert summary is not None
    assert "qwen3.5-35b" in summary
    assert "5-8" in summary


def test_cloud_model_profile() -> None:
    summary = summarize_capability("anthropic/claude-sonnet-4-6")
    assert summary is not None
    assert "sonnet" in summary


def test_unknown_model_returns_none() -> None:
    assert summarize_capability("unknown/mystery-model") is None


def test_summary_format() -> None:
    summary = summarize_capability("qwen3.5-4b-swarm")
    assert summary is not None
    assert "(n=" in summary
    assert "files optimal" in summary
    assert "focused can reach" in summary


# ---------------------------------------------------------------------------
# _resolve_profile
# ---------------------------------------------------------------------------


def test_resolve_exact() -> None:
    profiles = {"llama-cpp/qwen3.5-35b": {"label": "test"}}
    assert _resolve_profile("llama-cpp/qwen3.5-35b", profiles) is not None


def test_resolve_segment() -> None:
    profiles = {"qwen3.5-35b": {"label": "test"}}
    assert _resolve_profile("llama-cpp/qwen3.5-35b", profiles) is not None


def test_resolve_strip_swarm() -> None:
    profiles = {"qwen3.5-4b": {"label": "test"}}
    assert _resolve_profile("llama-cpp-swarm/qwen3.5-4b-swarm", profiles) is not None


def test_resolve_no_match() -> None:
    profiles = {"something-else": {"label": "test"}}
    assert _resolve_profile("llama-cpp/qwen3.5-35b", profiles) is None


# ---------------------------------------------------------------------------
# Runtime override merge
# ---------------------------------------------------------------------------


def test_runtime_override_merges() -> None:
    clear_cache()
    with tempfile.TemporaryDirectory() as tmpdir:
        override_dir = Path(tmpdir) / ".formicos" / "runtime"
        override_dir.mkdir(parents=True)
        (override_dir / "capability_profiles.json").write_text(json.dumps({
            "profiles": {
                "qwen3.5-4b-swarm": {"observations": 50},
                "custom-model": {
                    "label": "custom", "observations": 10,
                    "optimal_files": "1-2", "single_file_penalty": 0.0,
                    "focused_quality": 0.6,
                },
            },
        }))
        summary = summarize_capability("qwen3.5-4b-swarm", data_dir=tmpdir)
        assert summary is not None
        assert "(n=50" in summary

        clear_cache()
        summary2 = summarize_capability("custom-model", data_dir=tmpdir)
        assert summary2 is not None
        assert "custom" in summary2


# ---------------------------------------------------------------------------
# Granularity classification
# ---------------------------------------------------------------------------


def test_classify_granularity_single() -> None:
    assert _classify_granularity(1) == "focused_single"


def test_classify_granularity_fine_split() -> None:
    assert _classify_granularity(2) == "fine_split"
    assert _classify_granularity(3) == "fine_split"


def test_classify_granularity_grouped_small() -> None:
    assert _classify_granularity(5) == "grouped_small"


def test_classify_granularity_grouped_medium() -> None:
    assert _classify_granularity(10) == "grouped_medium"


# ---------------------------------------------------------------------------
# Dominant worker model
# ---------------------------------------------------------------------------


def test_dominant_worker_excludes_planner() -> None:
    usage = {
        "anthropic/claude-sonnet-4-6": {"input_tokens": 10000, "output_tokens": 5000},
        "llama-cpp/qwen3.5-35b": {"input_tokens": 20000, "output_tokens": 8000},
    }
    assert _dominant_worker_model(usage, "anthropic/claude-sonnet-4-6") == "llama-cpp/qwen3.5-35b"


def test_dominant_worker_falls_back_to_planner() -> None:
    usage = {"anthropic/claude-sonnet-4-6": {"input_tokens": 100, "output_tokens": 50}}
    assert _dominant_worker_model(usage, "anthropic/claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# get_capability_evidence (structured)
# ---------------------------------------------------------------------------


def test_evidence_shipped_only() -> None:
    clear_cache()
    ev = get_capability_evidence("qwen3.5-4b-swarm")
    assert ev is not None
    assert ev["source"] == "shipped"
    assert ev["evidence_tier"] == "prior_only"
    assert ev["quality_mean"] == 0.738
    assert "priors only" in ev["warnings"][0].lower()


def test_evidence_unknown_model() -> None:
    clear_cache()
    assert get_capability_evidence("unknown/model") is None


# ---------------------------------------------------------------------------
# Replay-derived overlays (with mock projections)
# ---------------------------------------------------------------------------


@dataclass
class _FakeOutcome:
    colony_id: str
    workspace_id: str
    thread_id: str = "t-1"
    succeeded: bool = True
    total_rounds: int = 4
    total_cost: float = 0.5
    duration_ms: int = 30000
    entries_extracted: int = 0
    entries_accessed: int = 0
    quality_score: float = 0.75
    caste_composition: list[str] = field(default_factory=lambda: ["coder"])
    strategy: str = "sequential"


@dataclass
class _FakeColony:
    model_assignments: dict[str, str] = field(default_factory=dict)
    target_files: list[str] = field(default_factory=list)


@dataclass
class _FakeBudget:
    model_usage: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class _FakeProjections:
    outcomes: dict[str, _FakeOutcome] = field(default_factory=dict)
    colonies: dict[str, _FakeColony] = field(default_factory=dict)
    budgets: dict[str, _FakeBudget] = field(default_factory=dict)


def _make_projections(n: int = 5) -> _FakeProjections:
    proj = _FakeProjections()
    for i in range(n):
        cid = f"c-{i}"
        proj.outcomes[cid] = _FakeOutcome(
            colony_id=cid, workspace_id="ws-1",
            quality_score=0.7 + i * 0.02, total_rounds=3 + i,
        )
        proj.colonies[cid] = _FakeColony(
            model_assignments={"queen": "anthropic/claude-sonnet-4-6", "coder": "llama-cpp/qwen3.5-35b"},
            target_files=[f"src/file{j}.py" for j in range(3)],
        )
        proj.budgets[cid] = _FakeBudget(model_usage={
            "anthropic/claude-sonnet-4-6": {"input_tokens": 500, "output_tokens": 200, "cost": 0.01},
            "llama-cpp/qwen3.5-35b": {"input_tokens": 5000, "output_tokens": 2000, "cost": 0.0},
        })
    return proj


def test_derive_overlays_basic() -> None:
    proj = _make_projections(5)
    overlays = derive_overlays_from_projections(proj, workspace_id="ws-1")  # type: ignore[arg-type]
    assert len(overlays) >= 1
    for _key, val in overlays.items():
        assert val["sample_count"] == 5
        assert val["evidence_tier"] == "moderate"
        assert val["quality_mean"] > 0


def test_derive_overlays_filters_workspace() -> None:
    proj = _make_projections(3)
    overlays = derive_overlays_from_projections(proj, workspace_id="ws-other")  # type: ignore[arg-type]
    assert len(overlays) == 0


def test_derive_overlays_high_evidence_tier() -> None:
    proj = _make_projections(12)
    overlays = derive_overlays_from_projections(proj, workspace_id="ws-1")  # type: ignore[arg-type]
    for _key, val in overlays.items():
        assert val["evidence_tier"] == "high"


def test_evidence_merged_with_replay() -> None:
    clear_cache()
    proj = _make_projections(5)
    ev = get_capability_evidence(
        "llama-cpp/qwen3.5-35b",
        projections=proj,  # type: ignore[arg-type]
        workspace_id="ws-1",
        planner_model="anthropic/claude-sonnet-4-6",
    )
    assert ev is not None
    assert ev["source"] in ("merged", "replay")
    assert ev["sample_count"] >= 3
    assert ev["evidence_tier"] in ("moderate", "high")
