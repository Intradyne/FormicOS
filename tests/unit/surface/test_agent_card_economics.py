"""Tests for Wave 75 B2: Agent Card economics block."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from formicos.surface.routes.protocols import _build_economics_block


@dataclass
class FakeColonyOutcome:
    colony_id: str
    workspace_id: str = "ws-1"
    thread_id: str = "t-1"
    succeeded: bool = True
    total_rounds: int = 3
    total_cost: float = 0.10
    duration_ms: int = 5000
    entries_extracted: int = 1
    entries_accessed: int = 2
    quality_score: float = 0.85
    caste_composition: list[str] = field(default_factory=lambda: ["coder"])
    strategy: str = "stigmergic"
    maintenance_source: str | None = None


@dataclass
class FakeColony:
    id: str
    completed_at: str = ""


class TestBuildEconomicsBlock:
    def _make_projections(
        self,
        outcomes: list[FakeColonyOutcome] | None = None,
        colonies: dict[str, FakeColony] | None = None,
    ) -> MagicMock:
        proj = MagicMock()
        proj.colony_outcomes = {
            o.colony_id: o for o in (outcomes or [])
        }
        proj.colonies = colonies or {}
        return proj

    def test_empty_outcomes(self) -> None:
        proj = self._make_projections()
        result = _build_economics_block(proj)
        assert result["contract_schema"] == "formicos/contribution-contract@1"
        assert result["historical_stats"]["tasks_completed_30d"] == 0
        assert result["historical_stats"]["acceptance_rate_30d"] == 0.0
        assert result["sponsorship_required"] is True
        assert result["licensing"]["code"] == "AGPL-3.0-only"

    def test_30_day_stats(self) -> None:
        now = datetime.now(tz=UTC)
        recent_ts = (now - timedelta(days=5)).isoformat()
        old_ts = (now - timedelta(days=60)).isoformat()

        outcomes = [
            FakeColonyOutcome(colony_id="c1", succeeded=True, total_cost=0.10, quality_score=0.9),
            FakeColonyOutcome(colony_id="c2", succeeded=False, total_cost=0.20, quality_score=0.5),
            FakeColonyOutcome(colony_id="c3", succeeded=True, total_cost=0.05, quality_score=0.8),
        ]
        colonies = {
            "c1": FakeColony(id="c1", completed_at=recent_ts),
            "c2": FakeColony(id="c2", completed_at=recent_ts),
            "c3": FakeColony(id="c3", completed_at=old_ts),  # outside 30-day window
        }
        proj = self._make_projections(outcomes, colonies)
        result = _build_economics_block(proj)

        stats = result["historical_stats"]
        assert stats["tasks_completed_30d"] == 2  # only c1 and c2
        assert stats["acceptance_rate_30d"] == 0.5  # 1 succeeded / 2 completed
        assert stats["median_cost_usd_30d"] == 0.15  # median of [0.10, 0.20]

    def test_all_succeeded(self) -> None:
        now = datetime.now(tz=UTC)
        ts = (now - timedelta(days=1)).isoformat()
        outcomes = [
            FakeColonyOutcome(colony_id="c1", succeeded=True, total_cost=0.10, quality_score=0.9),
        ]
        colonies = {"c1": FakeColony(id="c1", completed_at=ts)}
        proj = self._make_projections(outcomes, colonies)
        result = _build_economics_block(proj)

        assert result["historical_stats"]["acceptance_rate_30d"] == 1.0
