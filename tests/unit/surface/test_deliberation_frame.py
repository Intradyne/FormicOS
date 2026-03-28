"""Tests for _build_deliberation_frame (Wave 68 Track 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

from formicos.surface.projections import ColonyOutcome, ThreadProjection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS_ID = "ws-1"
THREAD_ID = "thread-1"


def _make_entry(
    workspace_id: str = WS_ID,
    domains: list[str] | None = None,
    alpha: float = 8.0,
    beta: float = 2.0,
) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "domains": domains or ["python"],
        "conf_alpha": alpha,
        "conf_beta": beta,
    }


def _make_outcome(
    workspace_id: str = WS_ID,
    succeeded: bool = True,
    strategy: str = "stigmergic",
    total_rounds: int = 3,
    total_cost: float = 0.0012,
) -> ColonyOutcome:
    return ColonyOutcome(
        colony_id="col-1",
        workspace_id=workspace_id,
        thread_id=THREAD_ID,
        succeeded=succeeded,
        total_rounds=total_rounds,
        total_cost=total_cost,
        duration_ms=1000,
        entries_extracted=1,
        entries_accessed=2,
        quality_score=0.8,
        caste_composition=["coder"],
        strategy=strategy,
        maintenance_source=None,
    )


def _make_thread(
    goal: str = "",
    colony_count: int = 0,
    completed: int = 0,
    failed: int = 0,
) -> ThreadProjection:
    return ThreadProjection(
        id=THREAD_ID,
        workspace_id=WS_ID,
        name="test",
        goal=goal,
        colony_count=colony_count,
        completed_colony_count=completed,
        failed_colony_count=failed,
    )


@dataclass
class FakeProjections:
    memory_entries: dict[str, dict[str, Any]] = field(
        default_factory=dict,
    )
    colony_outcomes: dict[str, ColonyOutcome] = field(
        default_factory=dict,
    )
    _thread: ThreadProjection | None = None

    def get_thread(
        self,
        workspace_id: str,
        thread_id: str,
    ) -> ThreadProjection | None:
        return self._thread


def _make_queen(
    projections: Any = None,
    app_state: Any = None,
) -> Any:
    """Build a minimal QueenAgent with mocked runtime."""
    from formicos.surface.queen_runtime import QueenAgent

    runtime = MagicMock()
    runtime.projections = projections or FakeProjections()
    runtime.castes = None
    runtime.settings.models.registry = []

    if app_state is not None:
        runtime.app.state = app_state
    else:
        runtime.app = None

    queen = QueenAgent.__new__(QueenAgent)
    queen._runtime = runtime
    return queen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeliberationFrame:
    def test_frame_includes_domains_and_outcomes(self) -> None:
        proj = FakeProjections(
            memory_entries={
                "e1": _make_entry(domains=["python", "testing"]),
                "e2": _make_entry(domains=["python"]),
            },
            colony_outcomes={
                "c1": _make_outcome(succeeded=True),
                "c2": _make_outcome(succeeded=False),
            },
        )
        queen = _make_queen(projections=proj)
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)

        assert "## Institutional Memory Coverage" in frame
        assert "python" in frame
        assert "## Recent Colony Outcomes" in frame
        assert "[ok]" in frame
        assert "[FAIL]" in frame

    def test_frame_caps_at_budget(self) -> None:
        """Frame must be cappable (caller enforces budget)."""
        proj = FakeProjections(
            memory_entries={
                f"e{i}": _make_entry(
                    domains=[f"domain-{i}"],
                )
                for i in range(50)
            },
        )
        queen = _make_queen(projections=proj)
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)
        # Frame is finite and non-empty
        assert len(frame) > 0
        # Caller caps at budget.thread_context * 4; here we just
        # verify the frame itself is bounded (top-10 domains).
        assert frame.count("entries, avg confidence") <= 10

    def test_deliberation_triggers_on_exploratory_message(
        self,
    ) -> None:
        """_DELIBERATION_RE should match exploratory phrasing."""
        from formicos.adapters.queen_intent_parser import (
            _DELIBERATION_RE,
        )

        assert _DELIBERATION_RE.search("I think we could try X")
        assert _DELIBERATION_RE.search(
            "here are some options for the migration"
        )
        assert not _DELIBERATION_RE.search("run tests now")

    def test_frame_empty_for_bare_workspace(self) -> None:
        proj = FakeProjections()
        queen = _make_queen(projections=proj)
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)
        assert frame == ""

    def test_frame_prefers_capability_metadata(self) -> None:
        """When addon manifests have content_kinds/path_globs,
        the frame labels corpus coverage by source type."""

        @dataclass
        class FakeTool:
            name: str = "search_docs"

        @dataclass
        class FakeManifest:
            name: str = "docs-index"
            description: str = "Documentation index"
            content_kinds: list[str] = field(
                default_factory=lambda: ["documentation"],
            )
            path_globs: list[str] = field(
                default_factory=lambda: [
                    "**/*.md",
                    "**/*.rst",
                ],
            )
            search_tool: str = "search_docs"
            tools: list[Any] = field(default_factory=list)

        app_state = MagicMock()
        app_state.addon_manifests = [FakeManifest()]

        proj = FakeProjections()
        queen = _make_queen(
            projections=proj, app_state=app_state,
        )
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)

        assert "## Addon Corpus Coverage" in frame
        assert "docs-index" in frame
        assert "documentation" in frame
        assert "**/*.md" in frame
        assert "search via search_docs" in frame

    def test_frame_falls_back_to_tool_descriptions(self) -> None:
        """Without capability metadata, falls back to tool names."""

        @dataclass
        class FakeTool:
            name: str = "semantic_search_code"

        @dataclass
        class FakeManifest:
            name: str = "codebase-index"
            description: str = "Code search"
            tools: list[Any] = field(
                default_factory=lambda: [FakeTool()],
            )

        app_state = MagicMock()
        app_state.addon_manifests = [FakeManifest()]

        proj = FakeProjections()
        queen = _make_queen(
            projections=proj, app_state=app_state,
        )
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)

        assert "codebase-index" in frame
        assert "semantic_search_code" in frame

    def test_thread_progress_included(self) -> None:
        proj = FakeProjections(
            _thread=_make_thread(
                goal="Migrate auth",
                colony_count=5,
                completed=3,
                failed=1,
            ),
        )
        queen = _make_queen(projections=proj)
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)

        assert "## Thread Progress" in frame
        assert "Migrate auth" in frame
        assert "5 total" in frame
        assert "3 completed" in frame

    @patch(
        "formicos.surface.queen_runtime.generate_briefing",
    )
    def test_active_alerts_included(
        self, mock_briefing: MagicMock,
    ) -> None:
        @dataclass
        class FakeInsight:
            severity: str = "warning"
            title: str = "Stale cluster"
            detail: str = "3 entries need refresh"
            category: str = "knowledge_health"

        mock_result = MagicMock()
        mock_result.insights = [FakeInsight()]
        mock_briefing.return_value = mock_result

        proj = FakeProjections()
        queen = _make_queen(projections=proj)
        frame = queen._build_deliberation_frame(WS_ID, THREAD_ID)

        assert "## Active Alerts" in frame
        assert "Stale cluster" in frame
