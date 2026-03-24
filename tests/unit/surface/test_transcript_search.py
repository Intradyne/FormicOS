"""Tests for transcript_search agent tool (Wave 31 B3).

Given: Completed colonies exist with task and output data.
When: transcript_search is called with a keyword query.
Then: Matching colony snippets are returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.surface.runtime import Runtime


@dataclass
class _FakeRound:
    """Minimal round projection for testing."""

    round_number: int = 1
    agent_outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class _FakeColony:
    """Minimal colony projection for testing."""

    id: str
    workspace_id: str
    task: str
    status: str = "completed"
    round_records: list[_FakeRound] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


def _make_runtime_with_colonies(
    colonies: dict[str, _FakeColony],
) -> MagicMock:
    """Build a mock runtime with colony projections."""
    runtime = MagicMock()
    projections = MagicMock()
    projections.colonies = colonies
    runtime.projections = projections
    return runtime


class TestTranscriptSearch:
    """Verify transcript_search callback returns matching colony snippets."""

    @pytest.mark.asyncio
    async def test_keyword_match_returns_colony(self) -> None:
        """Word-overlap fallback matches colony task text."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-alpha",
                workspace_id="ws-1",
                task="Implement authentication with JWT tokens",
            ),
            "col-2": _FakeColony(
                id="col-beta",
                workspace_id="ws-1",
                task="Write database migration scripts",
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        assert fn is not None
        result = await fn("authentication JWT", "ws-1", 3)
        assert "col-alph" in result
        assert "authentication" in result.lower()

    @pytest.mark.asyncio
    async def test_no_match_returns_message(self) -> None:
        """Query with no matching words returns 'no matching' message."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-alpha",
                workspace_id="ws-1",
                task="Implement authentication",
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("zzzznonexistent", "ws-1", 3)
        assert "no matching" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_message(self) -> None:
        """No completed colonies in workspace returns appropriate message."""
        runtime = _make_runtime_with_colonies({})

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("anything", "ws-1", 3)
        assert "no completed" in result.lower()

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self) -> None:
        """Results are limited to top_k entries."""
        runtime = _make_runtime_with_colonies({
            f"col-{i}": _FakeColony(
                id=f"col-{i:04d}",
                workspace_id="ws-1",
                task=f"Task about python coding pattern {i}",
            )
            for i in range(10)
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("python coding", "ws-1", 2)
        colony_count = result.count("[Colony ")
        assert colony_count <= 2

    @pytest.mark.asyncio
    async def test_artifacts_shown_in_output(self) -> None:
        """Colony with artifacts shows artifact count and types."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-art1",
                workspace_id="ws-1",
                task="Build the API endpoint",
                artifacts=[
                    {"artifact_type": "code", "id": "art-1"},
                    {"artifact_type": "test", "id": "art-2"},
                ],
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("API endpoint", "ws-1", 3)
        assert "2" in result
        assert "code" in result

    @pytest.mark.asyncio
    async def test_failed_colony_included(self) -> None:
        """Failed colonies are also searchable (status in completed|failed)."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-fail",
                workspace_id="ws-1",
                task="Deploy the microservice",
                status="failed",
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("deploy microservice", "ws-1", 3)
        assert "col-fail" in result
        assert "failed" in result

    @pytest.mark.asyncio
    async def test_other_workspace_excluded(self) -> None:
        """Colonies from other workspaces should not appear."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-other",
                workspace_id="ws-other",
                task="Implement feature X",
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("feature", "ws-1", 3)
        assert "no completed" in result.lower()

    @pytest.mark.asyncio
    async def test_round_output_included_in_search(self) -> None:
        """Agent outputs from round records are included in search corpus."""
        runtime = _make_runtime_with_colonies({
            "col-1": _FakeColony(
                id="col-round",
                workspace_id="ws-1",
                task="Generic task",
                round_records=[
                    _FakeRound(
                        round_number=1,
                        agent_outputs={"agent-1": "Implemented a Redis caching layer"},
                    ),
                ],
            ),
        })

        fn = Runtime.make_transcript_search_fn(runtime)
        result = await fn("Redis caching", "ws-1", 3)
        assert "col-roun" in result
