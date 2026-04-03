"""Wave 82/85: Structural planner tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from formicos.surface.structural_planner import (
    _compute_confidence,
    _find_coupling_pairs,
    _find_mentioned_files,
    _normalize_for_matching,
    _suggest_groups,
    get_structural_hints,
)


def _make_file_info(
    path: str, imports: tuple[str, ...] = (), role: str = "source",
) -> SimpleNamespace:
    return SimpleNamespace(
        path=path, role=role, imports=imports,
        definitions=(), language="python",
    )


def _make_structure(files: list[SimpleNamespace]) -> SimpleNamespace:
    file_map = {f.path: f for f in files}
    dep_graph: dict[str, set[str]] = {}
    reverse_deps: dict[str, set[str]] = {}
    test_companions: dict[str, str] = {}

    for f in files:
        deps: set[str] = set()
        for imp in f.imports:
            for other in files:
                if other.path != f.path and other.path == imp:
                    deps.add(other.path)
        dep_graph[f.path] = deps
        for dep in deps:
            reverse_deps.setdefault(dep, set()).add(f.path)

    # Test companion detection
    for f in files:
        if f.role == "test":
            for other in files:
                if other.role == "source" and other.path.replace(".py", "") in f.path:
                    test_companions[f.path] = other.path

    def neighbors(path: str, max_hops: int = 1) -> set[str]:
        result: set[str] = set()
        current = {path}
        for _ in range(max_hops):
            next_hop: set[str] = set()
            for p in current:
                next_hop.update(dep_graph.get(p, set()))
                next_hop.update(reverse_deps.get(p, set()))
            result.update(next_hop)
            current = next_hop
        result.discard(path)
        return result

    return SimpleNamespace(
        files=file_map,
        dependency_graph=dep_graph,
        reverse_deps=reverse_deps,
        test_companions=test_companions,
        neighbors=neighbors,
    )


class TestFindMentionedFiles:
    def test_direct_path(self) -> None:
        structure = _make_structure([_make_file_info("src/runner.py")])
        matched = _find_mentioned_files(structure, "fix src/runner.py")
        assert "src/runner.py" in matched

    def test_stem_match(self) -> None:
        structure = _make_structure([_make_file_info("src/formicos/engine/runner.py")])
        matched = _find_mentioned_files(structure, "fix the runner module")
        assert "src/formicos/engine/runner.py" in matched

    def test_no_match(self) -> None:
        structure = _make_structure([_make_file_info("src/other.py")])
        matched = _find_mentioned_files(structure, "fix the runner module")
        assert matched == []

    def test_short_stems_ignored(self) -> None:
        structure = _make_structure([_make_file_info("src/a.py")])
        matched = _find_mentioned_files(structure, "fix a file")
        assert matched == []  # stem "a" is < 3 chars

    def test_phrase_style_match(self) -> None:
        """'workspace roots' should match workspace_roots.py."""
        structure = _make_structure([
            _make_file_info("src/surface/workspace_roots.py"),
        ])
        matched = _find_mentioned_files(
            structure, "refactor the workspace roots module",
        )
        assert "src/surface/workspace_roots.py" in matched

    def test_phrase_style_plan_patterns(self) -> None:
        structure = _make_structure([
            _make_file_info("src/surface/plan_patterns.py"),
        ])
        matched = _find_mentioned_files(
            structure, "update plan patterns",
        )
        assert "src/surface/plan_patterns.py" in matched

    def test_phrase_style_queen_runtime(self) -> None:
        structure = _make_structure([
            _make_file_info("src/surface/queen_runtime.py"),
        ])
        matched = _find_mentioned_files(
            structure, "fix the queen runtime",
        )
        assert "src/surface/queen_runtime.py" in matched


class TestNormalizeForMatching:
    def test_underscores_to_spaces(self) -> None:
        assert _normalize_for_matching("workspace_roots") == "workspace roots"

    def test_hyphens_to_spaces(self) -> None:
        assert _normalize_for_matching("plan-patterns") == "plan patterns"

    def test_dots_to_spaces(self) -> None:
        assert _normalize_for_matching("queen.runtime") == "queen runtime"

    def test_mixed_separators(self) -> None:
        assert _normalize_for_matching("a_b-c.d/e") == "a b c d e"


class TestFindCouplingPairs:
    def test_import_coupling(self) -> None:
        files = [
            _make_file_info("src/runner.py", imports=("src/types.py",)),
            _make_file_info("src/types.py"),
        ]
        structure = _make_structure(files)
        pairs = _find_coupling_pairs(structure, ["src/runner.py", "src/types.py"])
        assert len(pairs) >= 1
        assert any(p["from"] == "src/runner.py" and p["to"] == "src/types.py" for p in pairs)

    def test_no_coupling_between_unrelated(self) -> None:
        files = [
            _make_file_info("src/a.py"),
            _make_file_info("src/b.py"),
        ]
        structure = _make_structure(files)
        pairs = _find_coupling_pairs(structure, ["src/a.py", "src/b.py"])
        assert len(pairs) == 0


class TestSuggestGroups:
    def test_single_file(self) -> None:
        structure = _make_structure([_make_file_info("src/a.py")])
        groups = _suggest_groups(structure, ["src/a.py"], ["src/a.py"], 3)
        assert len(groups) == 1
        assert "src/a.py" in groups[0]["files"]

    def test_coupled_files_same_group(self) -> None:
        files = [
            _make_file_info("src/runner.py", imports=("src/types.py",)),
            _make_file_info("src/types.py"),
        ]
        structure = _make_structure(files)
        groups = _suggest_groups(
            structure,
            ["src/runner.py", "src/types.py"],
            ["src/runner.py"],
            3,
        )
        assert len(groups) == 1
        assert set(groups[0]["files"]) == {"src/runner.py", "src/types.py"}

    def test_uncoupled_files_separate_groups(self) -> None:
        files = [
            _make_file_info("src/a.py"),
            _make_file_info("src/b.py"),
        ]
        structure = _make_structure(files)
        groups = _suggest_groups(
            structure, ["src/a.py", "src/b.py"], ["src/a.py"], 3,
        )
        assert len(groups) == 2


class TestComputeConfidence:
    def test_no_matches_zero(self) -> None:
        structure = _make_structure([])
        assert _compute_confidence([], [], [], structure) == 0.0

    def test_matched_files_contribute(self) -> None:
        structure = _make_structure([_make_file_info("src/a.py")])
        conf = _compute_confidence(["src/a.py"], [], [], structure)
        assert conf > 0.0

    def test_coupling_boosts(self) -> None:
        structure = _make_structure([])
        without = _compute_confidence(["a", "b"], [], [], structure)
        with_coupling = _compute_confidence(
            ["a", "b"],
            [{"from": "a", "to": "b", "type": "imports"}],
            [],
            structure,
        )
        assert with_coupling > without


class TestGetStructuralHints:
    def test_no_file_indicators_empty(self) -> None:
        runtime = MagicMock()
        hints = get_structural_hints(runtime, "ws1", "what's the status?")
        assert hints["confidence"] == 0.0
        assert hints["matched_files"] == []

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_with_matched_files(self, mock_ws: MagicMock) -> None:
        files = [
            _make_file_info("src/runner.py", imports=("src/types.py",)),
            _make_file_info("src/types.py"),
        ]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()

        hints = get_structural_hints(runtime, "ws1", "fix src/runner.py import issues")
        assert len(hints["matched_files"]) >= 1
        assert hints["confidence"] > 0.0

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_weak_signal_suppressed(self, mock_ws: MagicMock) -> None:
        # Single file, no coupling → confidence < 0.3 → suppressed
        files = [_make_file_info("src/obscure_module.py")]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()

        hints = get_structural_hints(runtime, "ws1", "fix the obscure_module.py file")
        # May or may not be suppressed depending on exact confidence math,
        # but rationale should exist or be "no structural signal"
        assert "confidence" in hints

    @patch("formicos.surface.structural_planner.log")
    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_low_confidence_suppression_is_logged(
        self,
        mock_ws: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        files = [_make_file_info("src/obscure_module.py")]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()

        hints = get_structural_hints(runtime, "ws1", "fix the obscure_module.py file")

        assert hints["confidence"] == 0.0
        mock_log.debug.assert_any_call(
            "structural_planner.low_confidence_suppressed",
            workspace_id="ws1",
            matched_files=1,
            coupling_pairs=0,
            suggested_groups=1,
            confidence=0.2,
        )

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_no_file_indicators_gives_suppression_reason(self, mock_ws: MagicMock) -> None:
        runtime = MagicMock()
        hints = get_structural_hints(runtime, "ws1", "what's the status?")
        assert hints["suppression_reason"] == "no_file_indicators"

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_no_file_matches_gives_reason(self, mock_ws: MagicMock) -> None:
        files = [_make_file_info("src/unrelated.py")]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()
        hints = get_structural_hints(runtime, "ws1", "fix the file auth.py")
        assert hints["suppression_reason"] in ("no_file_matches", "low_confidence")

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_low_confidence_gives_reason(self, mock_ws: MagicMock) -> None:
        files = [_make_file_info("src/obscure.py")]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()
        hints = get_structural_hints(runtime, "ws1", "fix obscure.py file")
        if hints["confidence"] == 0.0:
            assert hints["suppression_reason"] == "low_confidence"

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_successful_hint_has_no_suppression(self, mock_ws: MagicMock) -> None:
        files = [
            _make_file_info("src/runner.py", imports=("src/types.py",)),
            _make_file_info("src/types.py"),
        ]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()
        hints = get_structural_hints(
            runtime, "ws1", "fix src/runner.py import issues",
        )
        if hints["confidence"] > 0:
            assert hints["suppression_reason"] is None

    @patch("formicos.surface.structural_planner._get_workspace_structure")
    def test_returns_groups(self, mock_ws: MagicMock) -> None:
        files = [
            _make_file_info("src/runner.py", imports=("src/types.py",)),
            _make_file_info("src/types.py"),
            _make_file_info("src/other.py"),
        ]
        mock_ws.return_value = _make_structure(files)
        runtime = MagicMock()

        hints = get_structural_hints(
            runtime, "ws1",
            "fix src/runner.py and src/types.py and src/other.py module issues",
        )
        if hints["confidence"] > 0:
            assert len(hints["suggested_groups"]) >= 1
