"""Wave 84.5 Track B: Queen planning evaluation harness.

Two layers:
- Deterministic scoring on fixture/captured plans (default, fast, no LLM)
- Optional live Queen capture mode behind FORMICOS_LIVE_EVAL=1

The golden prompt set covers fast_path, single_colony, parallel_dag,
and no-spawn (Q&A) routes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from formicos.engine.playbook_loader import clear_cache
from formicos.surface.queen_runtime import (
    _looks_like_colony_work,
    _prefer_single_colony_route,
)

# ── Golden prompt set ──

@dataclass
class GoldenPrompt:
    prompt: str
    expected_route: str  # "fast_path" | "single_colony" | "parallel_dag" | "none"
    expected_files: list[str] = field(default_factory=list)
    min_colonies: int = 0
    max_colonies: int = 0
    expected_task_class: str = ""


GOLDEN_PROMPTS: list[GoldenPrompt] = [
    # Simple single-file tasks — colony work detected, policy routes
    # single_colony (the Queen then uses fast_path when spawning)
    GoldenPrompt(
        prompt="Write tests for checkpoint.py",
        expected_route="single_colony",
        expected_files=["checkpoint.py", "test_checkpoint.py"],
        expected_task_class="code_implementation",
    ),
    GoldenPrompt(
        prompt="Fix the SSRF validator to block RFC 1918 ranges",
        expected_route="single_colony",
        expected_files=["ssrf_validate.py"],
        expected_task_class="code_implementation",
    ),
    GoldenPrompt(
        prompt="Fix the typo in README.md",
        expected_route="single_colony",
        expected_files=["README.md"],
        expected_task_class="code_implementation",
    ),
    GoldenPrompt(
        prompt="Add error handling to the save_pattern function",
        expected_route="single_colony",
        expected_files=["plan_patterns.py"],
        expected_task_class="code_implementation",
    ),

    # Multi-file tasks
    # Note: "multi-file" is simple by word count, colony work is detected,
    # and _prefer_single routes it to single_colony via policy.
    GoldenPrompt(
        prompt="Build a multi-file addon with scanner, coverage, quality, handlers, and tests",
        expected_route="single_colony",
        expected_files=["scanner.py", "coverage.py", "quality.py", "handlers.py"],
        expected_task_class="code_implementation",
    ),
    GoldenPrompt(
        prompt=(
            "Refactor the auth module across runner.py, "
            "types.py, colony_manager.py, and runtime.py"
        ),
        expected_route="parallel_dag",
        expected_files=["runner.py", "types.py", "colony_manager.py", "runtime.py"],
        min_colonies=2,
        expected_task_class="generic",
    ),
    GoldenPrompt(
        prompt="Implement federation push, pull, and conflict resolution across 3 modules",
        expected_route="parallel_dag",
        min_colonies=2,
        expected_task_class="code_implementation",
    ),

    # Single colony — 2-file refactor should be fast_path/single, not DAG
    GoldenPrompt(
        prompt=(
            "Consolidate workspace root resolution in "
            "runner.py to use workspace_roots.py"
        ),
        expected_route="single_colony",
        expected_files=["runner.py", "workspace_roots.py"],
        expected_task_class="generic",
    ),
    GoldenPrompt(
        prompt="Improve the auth module",
        expected_route="single_colony",
        expected_task_class="generic",
    ),

    # Research / design — no colony_work markers → fast_path via policy
    GoldenPrompt(
        prompt="Research best practices for async event-loop debugging in Python",
        expected_route="fast_path",
        expected_task_class="research",
    ),

    # Q&A — not colony work → fast_path via policy
    GoldenPrompt(
        prompt="What is the status of colony X?",
        expected_route="fast_path",
        expected_task_class="generic",
    ),
    GoldenPrompt(
        prompt="How many events are in the union?",
        expected_route="none",
        expected_task_class="generic",
    ),
    GoldenPrompt(
        prompt="Hello",
        expected_route="none",
        expected_task_class="generic",
    ),
]


# ── Deterministic scoring ──

@dataclass
class RoutingScore:
    prompt: str
    task_class: str
    complexity: str
    is_colony_work: bool
    prefers_single: bool
    inferred_route: str
    expected_route: str
    route_correct: bool
    playbook_hint: str | None
    deliverable_coverage: float  # 0.0-1.0
    coherent: bool  # all signals agree


def score_prompt(gp: GoldenPrompt) -> RoutingScore:
    """Score a single golden prompt via the consolidated planning policy."""
    from formicos.surface.planning_policy import decide_planning_route

    clear_cache()
    decision = decide_planning_route(gp.prompt)
    task_class = decision.task_class
    complexity = decision.complexity
    colony_work = _looks_like_colony_work(gp.prompt)
    single = _prefer_single_colony_route(gp.prompt)
    hint = decision.playbook_hint

    # Map fast_path to "none" when classifiers say it's not colony work
    inferred = "none" if decision.route == "fast_path" and not colony_work else decision.route

    route_correct = inferred == gp.expected_route

    # Deliverable coverage: how many expected files appear in the hint?
    covered = 0
    if gp.expected_files and hint:
        for f in gp.expected_files:
            stem = f.rsplit(".", 1)[0] if "." in f else f
            if stem.lower() in hint.lower():
                covered += 1
        deliverable_coverage = covered / len(gp.expected_files)
    else:
        deliverable_coverage = 1.0 if not gp.expected_files else 0.0

    # Coherence: do all signals agree?
    coherent = True
    if not colony_work and gp.expected_route != "none":
        coherent = False
    if single and gp.expected_route == "parallel_dag":
        coherent = False
    if complexity == "complex" and gp.expected_route == "fast_path":
        coherent = False

    return RoutingScore(
        prompt=gp.prompt,
        task_class=task_class,
        complexity=complexity,
        is_colony_work=colony_work,
        prefers_single=single,
        inferred_route=inferred,
        expected_route=gp.expected_route,
        route_correct=route_correct,
        playbook_hint=hint,
        deliverable_coverage=deliverable_coverage,
        coherent=coherent,
    )


# ── Deterministic tests (default, no LLM) ──

class TestDeterministicEval:
    """Fixture-driven eval — fast, no LLM."""

    @pytest.fixture(autouse=True)
    def _clear(self) -> None:
        clear_cache()

    def test_all_prompts_score(self) -> None:
        """Every golden prompt should produce a valid score."""
        for gp in GOLDEN_PROMPTS:
            score = score_prompt(gp)
            assert score.task_class, f"No task class for: {gp.prompt}"
            assert score.complexity in ("simple", "complex")
            assert score.inferred_route in ("none", "fast_path", "single_colony", "parallel_dag")

    def test_route_accuracy(self) -> None:
        """At least 80% of golden prompts should route correctly."""
        scores = [score_prompt(gp) for gp in GOLDEN_PROMPTS]
        correct = sum(1 for s in scores if s.route_correct)
        accuracy = correct / len(scores)
        assert accuracy >= 0.80, (
            f"Route accuracy {accuracy:.0%} < 80%. Misrouted: "
            + ", ".join(
                f"{s.prompt!r} ({s.inferred_route} != {s.expected_route})"
                for s in scores
                if not s.route_correct
            )
        )

    def test_no_spawn_prompts_classified_correctly(self) -> None:
        """Q&A prompts should not be classified as colony work."""
        for gp in GOLDEN_PROMPTS:
            if gp.expected_route == "none":
                score = score_prompt(gp)
                assert not score.is_colony_work, (
                    f"Q&A prompt classified as colony work: {gp.prompt!r}"
                )

    def test_complex_tasks_not_single(self) -> None:
        """Parallel DAG tasks should not prefer single colony."""
        for gp in GOLDEN_PROMPTS:
            if gp.expected_route == "parallel_dag":
                score = score_prompt(gp)
                assert not score.prefers_single, (
                    f"DAG task prefers single: {gp.prompt!r}"
                )

    def test_task_class_matches_expected(self) -> None:
        """When expected_task_class is set, it should match."""
        for gp in GOLDEN_PROMPTS:
            if gp.expected_task_class:
                score = score_prompt(gp)
                assert score.task_class == gp.expected_task_class, (
                    f"Task class mismatch for {gp.prompt!r}: "
                    f"{score.task_class} != {gp.expected_task_class}"
                )

    def test_summary_report(self) -> None:
        """Generate a summary report (always passes, output is informational)."""
        scores = [score_prompt(gp) for gp in GOLDEN_PROMPTS]
        correct = sum(1 for s in scores if s.route_correct)
        coherent = sum(1 for s in scores if s.coherent)
        report = {
            "total_prompts": len(scores),
            "route_accuracy": f"{correct}/{len(scores)}",
            "coherence_rate": f"{coherent}/{len(scores)}",
            "misrouted": [
                {"prompt": s.prompt, "expected": s.expected_route, "got": s.inferred_route}
                for s in scores
                if not s.route_correct
            ],
        }
        # Print for visibility in test output
        print(json.dumps(report, indent=2))


# ── Live LLM tests (optional, gated) ──

@pytest.mark.live_eval
class TestLiveEval:
    """Live Queen capture — requires FORMICOS_LIVE_EVAL=1 and running stack."""

    def test_live_policy_captures_route(self) -> None:
        """Prove the planning policy can be invoked on real prompts.

        This is a bounded smoke test: it calls ``decide_planning_route``
        on a subset of golden prompts and verifies the result is scoreable.
        No actual LLM call — just the full policy path including playbook
        and capability profile loading.
        """
        import httpx

        from formicos.surface.planning_policy import decide_planning_route

        # Quick health check — skip if stack is not up
        try:
            resp = httpx.get("http://localhost:8080/health", timeout=3)
            if resp.status_code != 200:
                pytest.skip("FormicOS stack not healthy")
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("FormicOS stack not reachable")

        # Exercise the full policy path
        results: list[dict[str, str]] = []
        for gp in GOLDEN_PROMPTS[:5]:
            decision = decide_planning_route(gp.prompt)
            results.append({
                "prompt": gp.prompt[:60],
                "route": decision.route,
                "task_class": decision.task_class,
                "complexity": decision.complexity,
            })

        assert len(results) == 5
        for r in results:
            assert r["route"] in ("fast_path", "single_colony", "parallel_dag")
        print(json.dumps(results, indent=2))
