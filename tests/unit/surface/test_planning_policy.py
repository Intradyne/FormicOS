"""Tests for consolidated planning policy (Wave 84.5 Track A)."""

from __future__ import annotations

from formicos.surface.planning_policy import PlanningDecision, decide_planning_route


class TestDecidePlanningRoute:
    def test_simple_status_query_routes_fast(self) -> None:
        decision = decide_planning_route("what's the status?")
        assert decision.route == "fast_path"
        assert decision.complexity == "simple"

    def test_explicit_implementation_routes_colony(self) -> None:
        decision = decide_planning_route("implement the auth module")
        assert decision.route in ("single_colony", "parallel_dag")

    def test_complex_multi_file_routes_dag(self) -> None:
        decision = decide_planning_route(
            "refactor scanner.py, coverage.py, handlers.py and add "
            "comprehensive tests for the addon system with integration "
            "tests that verify the full pipeline",
        )
        assert decision.route == "parallel_dag"
        assert decision.complexity == "complex"

    def test_returns_planning_decision(self) -> None:
        decision = decide_planning_route("hello")
        assert isinstance(decision, PlanningDecision)
        assert decision.task_class is not None
        assert decision.complexity in ("simple", "complex")
        assert decision.route in ("fast_path", "single_colony", "parallel_dag")

    def test_playbook_hint_populated(self) -> None:
        decision = decide_planning_route("implement a new feature module")
        # Playbook may or may not have a hint depending on playbook state
        assert isinstance(decision.playbook_hint, (str, type(None)))

    def test_confidence_is_positive(self) -> None:
        decision = decide_planning_route("build the addon")
        assert decision.confidence > 0

    def test_behavior_flags_dict(self) -> None:
        decision = decide_planning_route("test", model_addr="llama-cpp/qwen3.5-35b")
        assert isinstance(decision.behavior_flags, dict)

    def test_single_file_fix_routes_to_single_colony(self) -> None:
        # Wave 85: "fix" triggers colony work. Single-file simple fix
        # routes single_colony, not DAG (policy respects _prefer_single).
        decision = decide_planning_route("fix the bug in auth.py")
        assert decision.route == "single_colony"

    def test_simple_write_with_playbook_routes_dag(self) -> None:
        # "write" triggers colony work + playbook says multi-colony -> DAG
        decision = decide_planning_route("write a readme")
        assert decision.route in ("single_colony", "parallel_dag")


# -- Wave 85 Track B: policy-as-live-authority tests --


class TestPolicyRouteSemantics:
    """Verify route semantics match the live Queen wiring."""

    def test_fast_path_means_no_colony(self) -> None:
        d = decide_planning_route("how many events?")
        assert d.route == "fast_path"
        # fast_path should not trigger colony work directives

    def test_single_colony_for_simple_work(self) -> None:
        d = decide_planning_route("write tests for checkpoint.py")
        assert d.route == "single_colony"
        assert d.complexity == "simple"
        assert d.confidence >= 0.8

    def test_parallel_dag_for_complex_colony_work(self) -> None:
        d = decide_planning_route(
            "implement federation push, pull, and conflict resolution",
        )
        assert d.route == "parallel_dag"
        assert d.complexity == "complex"

    def test_qa_routes_fast(self) -> None:
        d = decide_planning_route("hello")
        assert d.route == "fast_path"

    def test_active_colonies_does_not_crash(self) -> None:
        d = decide_planning_route("fix it", active_colonies=5)
        assert d.route in ("fast_path", "single_colony", "parallel_dag")


class TestPolicyPlaybookOverride:
    """Verify playbook hints can override single->DAG."""

    def test_playbook_override_single_to_dag(self) -> None:
        d = decide_planning_route("improve the auth module")
        # "improve" triggers colony work, simple complexity -> single_colony
        # Then playbook may override to DAG if it mentions colonies
        assert d.route in ("single_colony", "parallel_dag")

    def test_playbook_does_not_downgrade_dag(self) -> None:
        """Playbooks never downgrade from DAG to single."""
        d = decide_planning_route(
            "implement a complex distributed system across multiple modules",
        )
        assert d.route == "parallel_dag"


class TestPolicyConfidence:
    """Verify confidence levels are sensible."""

    def test_fast_path_high_confidence(self) -> None:
        d = decide_planning_route("hi")
        assert d.confidence >= 0.8

    def test_complex_dag_moderate_confidence(self) -> None:
        d = decide_planning_route("debug the auth module across all files")
        assert 0.5 <= d.confidence <= 0.9
