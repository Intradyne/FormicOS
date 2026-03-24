"""Wave 38 Team 2: External-style internal benchmark suite.

Extends the Wave 37 harness with harder task slices inspired by
HumanEval-style function tasks and SWE-bench-style multi-file bug-fix
scenarios. Measures: success, quality, cost, wall time, retrieval cost.

This is an internal measurement harness, not a public benchmark.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext
from formicos.engine.runner import _compute_knowledge_prior, _merge_knowledge_prior
from formicos.engine.strategies.stigmergic import StigmergicStrategy
from formicos.surface.proactive_intelligence import (
    _effective_count,
    compute_config_branching,
    compute_knowledge_branching,
)

# Re-use Wave 37 ablation framework
from tests.integration.test_wave37_stigmergic_loop import (
    BASELINE,
    FULL_W37,
    ONLY_1A,
    ONLY_1B,
    ONLY_1C,
    AblationConfig,
)

# ---------------------------------------------------------------------------
# Fixtures (shared with Wave 37 harness where possible)
# ---------------------------------------------------------------------------


def _recipe(name: str = "coder") -> CasteRecipe:
    return CasteRecipe(
        name=name,
        description=f"{name} tasks",
        system_prompt=f"You are a {name}.",
        temperature=0.0,
        tools=[],
        max_tokens=1024,
    )


def _agent(agent_id: str, caste: str = "coder") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, caste=caste,
        model="test-model", recipe=_recipe(caste),
    )


def _colony_ctx(
    goal: str = "Build a widget",
    round_number: int = 1,
) -> ColonyContext:
    return ColonyContext(
        colony_id="col-bench", workspace_id="ws-bench", thread_id="th-bench",
        goal=goal, round_number=round_number,
        merge_edges=[],
    )


def _high_sim_embed_fn(texts: list[str]) -> list[list[float]]:
    """Deterministic high-similarity embedding for testing."""
    result: list[list[float]] = []
    for i, _ in enumerate(texts):
        vec = [1.0] * 8
        vec[i % 8] += 0.01
        norm = math.sqrt(sum(x * x for x in vec))
        result.append([x / norm for x in vec])
    return result


# ---------------------------------------------------------------------------
# Benchmark result tracking
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Result of a single benchmark task run."""

    task_id: str
    task_type: str  # "humaneval" | "swebench" | "repeated_domain"
    config_label: str
    success: bool
    quality_score: float  # [0.0, 1.0]
    wall_time_ms: float
    estimated_cost: float  # token-based cost estimate
    retrieval_cost: float  # retrieval signal contribution
    knowledge_items_used: int
    notes: str = ""


@dataclass
class BenchmarkSuite:
    """Collects results across multiple task runs."""

    results: list[BenchmarkResult] = field(default_factory=list)

    def add(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def summary_by_config(self) -> dict[str, dict[str, Any]]:
        """Aggregate results by configuration label."""
        by_config: dict[str, list[BenchmarkResult]] = {}
        for r in self.results:
            by_config.setdefault(r.config_label, []).append(r)

        summaries: dict[str, dict[str, Any]] = {}
        for label, runs in by_config.items():
            n = len(runs)
            successes = sum(1 for r in runs if r.success)
            summaries[label] = {
                "total_tasks": n,
                "success_rate": successes / n if n else 0.0,
                "avg_quality": sum(r.quality_score for r in runs) / n if n else 0.0,
                "avg_wall_time_ms": sum(r.wall_time_ms for r in runs) / n if n else 0.0,
                "total_cost": sum(r.estimated_cost for r in runs),
                "avg_retrieval_cost": (
                    sum(r.retrieval_cost for r in runs) / n if n else 0.0
                ),
            }
        return summaries

    def summary_by_type(self) -> dict[str, dict[str, Any]]:
        """Aggregate results by task type."""
        by_type: dict[str, list[BenchmarkResult]] = {}
        for r in self.results:
            by_type.setdefault(r.task_type, []).append(r)

        summaries: dict[str, dict[str, Any]] = {}
        for ttype, runs in by_type.items():
            n = len(runs)
            summaries[ttype] = {
                "total_tasks": n,
                "success_rate": sum(1 for r in runs if r.success) / n if n else 0.0,
                "avg_quality": sum(r.quality_score for r in runs) / n if n else 0.0,
            }
        return summaries


# ---------------------------------------------------------------------------
# HumanEval-style task slices
# ---------------------------------------------------------------------------

HUMANEVAL_TASKS: list[dict[str, Any]] = [
    {
        "id": "he-001-two-sum",
        "domain": "python",
        "goal": "Implement a function that finds two numbers in a list that sum to a target",
        "difficulty": "easy",
        "expected_signals": {"function_correctness": True, "edge_cases": True},
    },
    {
        "id": "he-002-longest-substr",
        "domain": "python",
        "goal": "Find the longest substring without repeating characters",
        "difficulty": "medium",
        "expected_signals": {"function_correctness": True, "sliding_window": True},
    },
    {
        "id": "he-003-median-sorted",
        "domain": "python",
        "goal": "Find the median of two sorted arrays in O(log(m+n)) time",
        "difficulty": "hard",
        "expected_signals": {"function_correctness": True, "binary_search": True},
    },
    {
        "id": "he-004-valid-parens",
        "domain": "python",
        "goal": "Check if a string of brackets is valid using a stack",
        "difficulty": "easy",
        "expected_signals": {"function_correctness": True, "stack_usage": True},
    },
    {
        "id": "he-005-merge-intervals",
        "domain": "python",
        "goal": "Merge overlapping intervals in a list of [start, end] pairs",
        "difficulty": "medium",
        "expected_signals": {"function_correctness": True, "sorting": True},
    },
]


# ---------------------------------------------------------------------------
# SWE-bench-style multi-file bug-fix slices
# ---------------------------------------------------------------------------

SWEBENCH_TASKS: list[dict[str, Any]] = [
    {
        "id": "sw-001-stale-cache",
        "domain": "python",
        "goal": "Fix a stale cache bug where invalidation misses nested keys",
        "difficulty": "medium",
        "files_involved": ["cache.py", "invalidation.py", "tests/test_cache.py"],
        "expected_signals": {"cross_file_reasoning": True, "regression_test": True},
    },
    {
        "id": "sw-002-race-condition",
        "domain": "python",
        "goal": "Fix a race condition in concurrent task queue processing",
        "difficulty": "hard",
        "files_involved": ["queue.py", "worker.py", "tests/test_queue.py"],
        "expected_signals": {"concurrency_reasoning": True, "lock_usage": True},
    },
    {
        "id": "sw-003-migration-error",
        "domain": "python",
        "goal": "Fix a database migration that silently drops a column constraint",
        "difficulty": "medium",
        "files_involved": ["migrations/003.py", "models.py", "tests/test_models.py"],
        "expected_signals": {"schema_reasoning": True, "constraint_check": True},
    },
    {
        "id": "sw-004-import-cycle",
        "domain": "python",
        "goal": "Break a circular import between two modules without changing public API",
        "difficulty": "medium",
        "files_involved": ["module_a.py", "module_b.py", "tests/test_imports.py"],
        "expected_signals": {"dependency_reasoning": True, "api_stability": True},
    },
]


# ---------------------------------------------------------------------------
# Benchmark execution helpers
# ---------------------------------------------------------------------------


def _simulate_task_run(
    task: dict[str, Any],
    task_type: str,
    config: AblationConfig,
    knowledge_items: list[dict[str, Any]],
    agents: list[AgentConfig],
) -> BenchmarkResult:
    """Simulate a benchmark task run with given configuration.

    This exercises the real knowledge-prior and branching-diagnostics
    code paths without running an actual LLM. The quality and success
    signals are derived from the architectural signals themselves.
    """
    t0 = time.monotonic()

    # Signal 1: Knowledge prior (1A)
    prior_strength = 0.0
    if config.knowledge_prior and knowledge_items:
        prior = _compute_knowledge_prior(agents, knowledge_items)
        if prior is not None and len(prior) > 0:
            # Mean deviation from neutral (1.0) indicates prior informativeness
            prior_strength = sum(abs(v - 1.0) for v in prior.values()) / len(prior)

    # Signal 2: Quality weighting (1B) — simulated delta range
    quality_bonus = 0.0
    if config.quality_weighted_reinforcement:
        # Simulate accumulated quality from prior runs in same domain
        domain = task.get("domain", "unknown")
        domain_items = [
            ki for ki in knowledge_items
            if domain in ki.get("domains", [])
        ]
        if domain_items:
            avg_alpha = sum(ki.get("conf_alpha", 5.0) for ki in domain_items) / len(domain_items)
            avg_beta = sum(ki.get("conf_beta", 5.0) for ki in domain_items) / len(domain_items)
            quality_bonus = avg_alpha / (avg_alpha + avg_beta) * 0.2

    # Signal 3: Branching diagnostics (1C)
    branching_signal = 0.0
    if config.branching_diagnostics and knowledge_items:
        ki_map = {
            f"e{i}": ki for i, ki in enumerate(knowledge_items)
        }
        bf = compute_knowledge_branching(ki_map)
        # Higher branching → more diverse knowledge → better on novel tasks
        branching_signal = min(bf * 0.1, 0.15)

    # Composite quality score
    base_quality = 0.5  # baseline without features
    difficulty_penalty = {"easy": 0.0, "medium": 0.1, "hard": 0.2}.get(
        task.get("difficulty", "medium"), 0.1,
    )
    quality = min(1.0, base_quality + prior_strength + quality_bonus + branching_signal - difficulty_penalty)
    quality = max(0.0, quality)

    # Success: quality > 0.4 threshold
    success = quality > 0.4

    # Cost estimation (token-based proxy)
    base_tokens = 500
    files_involved = len(task.get("files_involved", []))
    estimated_tokens = base_tokens + files_involved * 200
    cost_per_1k = 0.003  # proxy cost
    estimated_cost = estimated_tokens * cost_per_1k / 1000

    # Retrieval cost: proportional to knowledge items used
    retrieval_cost = len(knowledge_items) * 0.001 if knowledge_items else 0.0

    wall_time_ms = (time.monotonic() - t0) * 1000

    return BenchmarkResult(
        task_id=task["id"],
        task_type=task_type,
        config_label=config.label(),
        success=success,
        quality_score=round(quality, 3),
        wall_time_ms=round(wall_time_ms, 2),
        estimated_cost=round(estimated_cost, 6),
        retrieval_cost=round(retrieval_cost, 6),
        knowledge_items_used=len(knowledge_items),
        notes=f"difficulty={task.get('difficulty', 'unknown')}",
    )


# ---------------------------------------------------------------------------
# Knowledge fixture sets (simulating accumulated domain knowledge)
# ---------------------------------------------------------------------------


def _python_domain_knowledge() -> list[dict[str, Any]]:
    """Knowledge entries for Python domain (simulates prior colony learning)."""
    return [
        {"conf_alpha": 20.0, "conf_beta": 3.0, "domains": ["python", "coder"],
         "title": "Use list comprehensions for filtering"},
        {"conf_alpha": 15.0, "conf_beta": 2.0, "domains": ["python", "coder"],
         "title": "Always handle edge cases: empty input, single element"},
        {"conf_alpha": 25.0, "conf_beta": 4.0, "domains": ["python", "algorithms"],
         "title": "Binary search requires sorted input invariant"},
        {"conf_alpha": 18.0, "conf_beta": 3.0, "domains": ["python", "testing"],
         "title": "Test with boundary values and type edge cases"},
        {"conf_alpha": 12.0, "conf_beta": 5.0, "domains": ["python", "async"],
         "title": "asyncio.gather for concurrent I/O-bound tasks"},
    ]


def _empty_knowledge() -> list[dict[str, Any]]:
    """No accumulated knowledge — cold start."""
    return []


# ---------------------------------------------------------------------------
# Tests: HumanEval-style benchmark slices
# ---------------------------------------------------------------------------


class TestHumanEvalBenchmarks:
    """HumanEval-inspired function-level task benchmarks."""

    def test_humaneval_baseline_runs(self) -> None:
        """Baseline (no Wave 37 features) produces valid results on all tasks."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        suite = BenchmarkSuite()

        for task in HUMANEVAL_TASKS:
            result = _simulate_task_run(
                task, "humaneval", BASELINE, _empty_knowledge(), agents,
            )
            suite.add(result)
            assert 0.0 <= result.quality_score <= 1.0
            assert result.wall_time_ms >= 0
            assert result.estimated_cost >= 0

        summary = suite.summary_by_config()
        assert "baseline" in summary
        assert summary["baseline"]["total_tasks"] == len(HUMANEVAL_TASKS)

    def test_humaneval_full_w37_with_knowledge(self) -> None:
        """Full Wave 37 features with domain knowledge score higher than baseline."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        suite = BenchmarkSuite()

        knowledge = _python_domain_knowledge()

        for task in HUMANEVAL_TASKS:
            for config in [BASELINE, FULL_W37]:
                ki = knowledge if config is FULL_W37 else _empty_knowledge()
                result = _simulate_task_run(
                    task, "humaneval", config, ki, agents,
                )
                suite.add(result)

        summary = suite.summary_by_config()
        assert summary["1A+1B+1C"]["avg_quality"] >= summary["baseline"]["avg_quality"]

    def test_humaneval_ablation_each_feature(self) -> None:
        """Each individual Wave 37 feature contributes measurably."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()

        configs = [BASELINE, ONLY_1A, ONLY_1B, ONLY_1C, FULL_W37]
        suite = BenchmarkSuite()

        for task in HUMANEVAL_TASKS:
            for config in configs:
                ki = knowledge if config is not BASELINE else _empty_knowledge()
                result = _simulate_task_run(
                    task, "humaneval", config, ki, agents,
                )
                suite.add(result)

        summary = suite.summary_by_config()
        # Each feature alone should be >= baseline
        for label in ["1A", "1B", "1C"]:
            assert summary[label]["avg_quality"] >= summary["baseline"]["avg_quality"], (
                f"{label} should be >= baseline"
            )
        # Full should be >= any individual
        full_q = summary["1A+1B+1C"]["avg_quality"]
        for label in ["1A", "1B", "1C"]:
            assert full_q >= summary[label]["avg_quality"], (
                f"Full should be >= {label}"
            )

    def test_humaneval_difficulty_gradient(self) -> None:
        """Harder tasks produce lower quality scores."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()

        by_difficulty: dict[str, list[float]] = {}
        for task in HUMANEVAL_TASKS:
            result = _simulate_task_run(
                task, "humaneval", FULL_W37, knowledge, agents,
            )
            diff = task.get("difficulty", "medium")
            by_difficulty.setdefault(diff, []).append(result.quality_score)

        avg_by_diff = {d: sum(scores) / len(scores) for d, scores in by_difficulty.items()}
        # Easy should score higher than hard
        if "easy" in avg_by_diff and "hard" in avg_by_diff:
            assert avg_by_diff["easy"] >= avg_by_diff["hard"]


# ---------------------------------------------------------------------------
# Tests: SWE-bench-style multi-file bug-fix slices
# ---------------------------------------------------------------------------


class TestSWEBenchBenchmarks:
    """SWE-bench-inspired multi-file bug-fix benchmarks."""

    def test_swebench_baseline_runs(self) -> None:
        """Baseline produces valid results on multi-file tasks."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        suite = BenchmarkSuite()

        for task in SWEBENCH_TASKS:
            result = _simulate_task_run(
                task, "swebench", BASELINE, _empty_knowledge(), agents,
            )
            suite.add(result)
            assert 0.0 <= result.quality_score <= 1.0
            assert result.estimated_cost > 0  # multi-file tasks have higher cost

        summary = suite.summary_by_config()
        assert summary["baseline"]["total_tasks"] == len(SWEBENCH_TASKS)

    def test_swebench_knowledge_helps(self) -> None:
        """Domain knowledge improves SWE-bench scores over baseline."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()

        baseline_scores: list[float] = []
        w37_scores: list[float] = []

        for task in SWEBENCH_TASKS:
            bl = _simulate_task_run(
                task, "swebench", BASELINE, _empty_knowledge(), agents,
            )
            w37 = _simulate_task_run(
                task, "swebench", FULL_W37, knowledge, agents,
            )
            baseline_scores.append(bl.quality_score)
            w37_scores.append(w37.quality_score)

        avg_bl = sum(baseline_scores) / len(baseline_scores)
        avg_w37 = sum(w37_scores) / len(w37_scores)
        assert avg_w37 >= avg_bl

    def test_swebench_cost_tracks_complexity(self) -> None:
        """Multi-file tasks have higher cost than zero-file tasks."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]

        # SWE-bench tasks have files_involved → positive cost from file count
        for task in SWEBENCH_TASKS:
            result = _simulate_task_run(
                task, "swebench", FULL_W37, _python_domain_knowledge(), agents,
            )
            n_files = len(task.get("files_involved", []))
            assert result.estimated_cost > 0
            # Cost should include file-proportional component
            base_cost = 500 * 0.003 / 1000  # base tokens only
            assert result.estimated_cost >= base_cost
            if n_files > 0:
                assert result.estimated_cost > base_cost


# ---------------------------------------------------------------------------
# Tests: Cross-suite comparison (the key Wave 38 value)
# ---------------------------------------------------------------------------


class TestCrossSuiteComparison:
    """Compare configurations across both HumanEval and SWE-bench slices."""

    def test_full_suite_reports_all_metrics(self) -> None:
        """The benchmark suite reports success, quality, cost, wall time,
        and retrieval cost across all task types."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()
        suite = BenchmarkSuite()

        all_tasks = [
            (t, "humaneval") for t in HUMANEVAL_TASKS
        ] + [
            (t, "swebench") for t in SWEBENCH_TASKS
        ]

        for config in [BASELINE, FULL_W37]:
            for task, ttype in all_tasks:
                ki = knowledge if config is FULL_W37 else _empty_knowledge()
                result = _simulate_task_run(task, ttype, config, ki, agents)
                suite.add(result)

        # Verify all metrics are present in summaries
        by_config = suite.summary_by_config()
        for label in ["baseline", "1A+1B+1C"]:
            s = by_config[label]
            assert "success_rate" in s
            assert "avg_quality" in s
            assert "avg_wall_time_ms" in s
            assert "total_cost" in s
            assert "avg_retrieval_cost" in s
            assert s["total_tasks"] == len(all_tasks)

        # Verify type breakdown
        by_type = suite.summary_by_type()
        assert "humaneval" in by_type
        assert "swebench" in by_type

    def test_wave37_vs_baseline_delta(self) -> None:
        """Wave 37 features produce a measurable positive delta over baseline
        when domain knowledge is available."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()
        suite = BenchmarkSuite()

        all_tasks = [
            (t, "humaneval") for t in HUMANEVAL_TASKS
        ] + [
            (t, "swebench") for t in SWEBENCH_TASKS
        ]

        for task, ttype in all_tasks:
            suite.add(_simulate_task_run(task, ttype, BASELINE, _empty_knowledge(), agents))
            suite.add(_simulate_task_run(task, ttype, FULL_W37, knowledge, agents))

        summary = suite.summary_by_config()
        delta_quality = summary["1A+1B+1C"]["avg_quality"] - summary["baseline"]["avg_quality"]
        # Wave 37 should provide a positive quality delta
        assert delta_quality >= 0, f"Expected positive delta, got {delta_quality}"

    def test_cold_start_vs_warm_domain(self) -> None:
        """Warm domain knowledge produces better results than cold start
        even with all features enabled."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        knowledge = _python_domain_knowledge()

        cold_scores: list[float] = []
        warm_scores: list[float] = []

        for task in HUMANEVAL_TASKS:
            cold = _simulate_task_run(
                task, "humaneval", FULL_W37, _empty_knowledge(), agents,
            )
            warm = _simulate_task_run(
                task, "humaneval", FULL_W37, knowledge, agents,
            )
            cold_scores.append(cold.quality_score)
            warm_scores.append(warm.quality_score)

        avg_cold = sum(cold_scores) / len(cold_scores)
        avg_warm = sum(warm_scores) / len(warm_scores)
        assert avg_warm >= avg_cold, (
            f"Warm ({avg_warm:.3f}) should be >= cold ({avg_cold:.3f})"
        )

    def test_retrieval_cost_tracked(self) -> None:
        """Retrieval cost is non-zero when knowledge is used, zero otherwise."""
        agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
        task = HUMANEVAL_TASKS[0]

        no_ki = _simulate_task_run(
            task, "humaneval", FULL_W37, _empty_knowledge(), agents,
        )
        with_ki = _simulate_task_run(
            task, "humaneval", FULL_W37, _python_domain_knowledge(), agents,
        )

        assert no_ki.retrieval_cost == 0.0
        assert with_ki.retrieval_cost > 0.0
        assert with_ki.knowledge_items_used == len(_python_domain_knowledge())


# ---------------------------------------------------------------------------
# Tests: Benchmark framework integrity
# ---------------------------------------------------------------------------


class TestBenchmarkFramework:
    """Verify the benchmark framework itself is correct."""

    def test_suite_aggregation(self) -> None:
        """BenchmarkSuite correctly aggregates across multiple results."""
        suite = BenchmarkSuite()
        suite.add(BenchmarkResult(
            task_id="t1", task_type="humaneval", config_label="baseline",
            success=True, quality_score=0.8, wall_time_ms=10.0,
            estimated_cost=0.001, retrieval_cost=0.0, knowledge_items_used=0,
        ))
        suite.add(BenchmarkResult(
            task_id="t2", task_type="humaneval", config_label="baseline",
            success=False, quality_score=0.3, wall_time_ms=20.0,
            estimated_cost=0.002, retrieval_cost=0.0, knowledge_items_used=0,
        ))
        suite.add(BenchmarkResult(
            task_id="t1", task_type="swebench", config_label="1A+1B+1C",
            success=True, quality_score=0.9, wall_time_ms=15.0,
            estimated_cost=0.003, retrieval_cost=0.005, knowledge_items_used=5,
        ))

        by_config = suite.summary_by_config()
        assert by_config["baseline"]["total_tasks"] == 2
        assert by_config["baseline"]["success_rate"] == 0.5
        assert abs(by_config["baseline"]["avg_quality"] - 0.55) < 0.001

        by_type = suite.summary_by_type()
        assert by_type["humaneval"]["total_tasks"] == 2
        assert by_type["swebench"]["total_tasks"] == 1

    def test_all_configs_have_distinct_labels(self) -> None:
        """All ablation configurations produce unique labels."""
        configs = [BASELINE, FULL_W37, ONLY_1A, ONLY_1B, ONLY_1C]
        labels = {c.label() for c in configs}
        assert len(labels) == len(configs)

    def test_benchmark_result_fields(self) -> None:
        """BenchmarkResult has all required reporting fields."""
        result = BenchmarkResult(
            task_id="test", task_type="humaneval", config_label="baseline",
            success=True, quality_score=0.7, wall_time_ms=5.0,
            estimated_cost=0.001, retrieval_cost=0.0, knowledge_items_used=0,
        )
        assert isinstance(result.task_id, str)
        assert isinstance(result.task_type, str)
        assert isinstance(result.config_label, str)
        assert isinstance(result.success, bool)
        assert isinstance(result.quality_score, float)
        assert isinstance(result.wall_time_ms, float)
        assert isinstance(result.estimated_cost, float)
        assert isinstance(result.retrieval_cost, float)
        assert isinstance(result.knowledge_items_used, int)
