"""Wave 87 Track C: capability-mode ladder golden tests."""

from __future__ import annotations

from formicos.surface.planning_policy import PlanningDecision, _classify_capability_mode


class TestCapabilityModeLadder:
    """Golden tests for the durability ladder classification."""

    def test_status_question_is_inspect(self) -> None:
        assert _classify_capability_mode("what's the status of the workspace?", False, "simple") == "inspect"

    def test_show_command_is_inspect(self) -> None:
        assert _classify_capability_mode("show me the recent colonies", False, "simple") == "inspect"

    def test_fix_test_is_edit_without_colony_work(self) -> None:
        assert _classify_capability_mode("fix the typo in README.md", False, "simple") == "edit"

    def test_fix_test_is_execute_with_colony_work(self) -> None:
        assert _classify_capability_mode("fix this failing test in checkpoint.py", True, "simple") == "execute"

    def test_audit_repo_is_execute(self) -> None:
        assert _classify_capability_mode("audit this repo for SSRF vulnerabilities", True, "complex") == "execute"

    def test_implement_feature_is_execute(self) -> None:
        assert _classify_capability_mode("implement a new health endpoint", True, "complex") == "execute"

    def test_build_dashboard_is_host(self) -> None:
        assert _classify_capability_mode("build me a dashboard I'll use daily", False, "complex") == "host"

    def test_monitor_github_is_host(self) -> None:
        # "monitor" is a host keyword; operate requires integration/service markers
        assert _classify_capability_mode("monitor GitHub and keep the dashboard updated", False, "complex") == "host"

    def test_greeting_is_reply(self) -> None:
        assert _classify_capability_mode("hello!", False, "simple") == "reply"

    def test_thanks_is_reply(self) -> None:
        # "looks" contains "look" but doesn't start with it — policy sees no strong signal
        assert _classify_capability_mode("thanks!", False, "simple") == "reply"

    def test_deploy_is_operate(self) -> None:
        assert _classify_capability_mode("deploy the service to production", False, "complex") == "operate"

    def test_schedule_webhook_is_operate(self) -> None:
        assert _classify_capability_mode("schedule a webhook check every hour", False, "simple") == "operate"

    def test_recurring_addon_is_host(self) -> None:
        assert _classify_capability_mode("create a recurring addon panel for memory stats", False, "simple") == "host"


class TestPlanningDecisionHasCapabilityMode:
    def test_decision_carries_mode(self) -> None:
        d = PlanningDecision(
            task_class="code", complexity="simple", route="fast_path",
            capability_mode="inspect",
        )
        assert d.capability_mode == "inspect"

    def test_decision_defaults_to_execute(self) -> None:
        d = PlanningDecision(task_class="", complexity="simple", route="fast_path")
        assert d.capability_mode == "execute"
