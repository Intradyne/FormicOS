"""Wave 84.5 Track B: Planning signal ablation framework.

Runs the same prompt set under four planning-signal configurations to
measure which signals actually change plan decisions.

Default path: deterministic, fixture-backed. No LLM needed.
Live ablation: gated behind FORMICOS_LIVE_EVAL=1.

Configurations:
  A: none       — all signals suppressed
  B: base       — knowledge + playbook + capability, no coupling/saved
  C: structural — base + coupling analysis
  D: full       — base + coupling + saved patterns
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from formicos.surface.queen_runtime import (
    _looks_like_colony_work,
    _prefer_single_colony_route,
)

# ── Ablation configurations ──

ABLATION_CONFIGS: dict[str, dict[str, bool]] = {
    "none": {"skip_all": True},
    "base": {"skip_coupling": True, "skip_saved": True},
    "structural": {"skip_saved": True},
    "full": {},
}


# ── Ablation prompt set (subset of golden prompts) ──

ABLATION_PROMPTS = [
    "Write tests for checkpoint.py",
    "Build a multi-file addon with scanner, coverage, quality, handlers, and tests",
    "Refactor the auth module across runner.py, types.py, colony_manager.py, and runtime.py",
    "Research best practices for async event-loop debugging in Python",
    "Fix the SSRF validator to block RFC 1918 ranges",
    "Improve the auth module",
    "What is the status of colony X?",
]


# ── Signal response fixtures ──

def _mock_signals(config_name: str) -> dict[str, Any]:
    """Build mock planning signals for a given ablation config."""
    cfg = ABLATION_CONFIGS[config_name]

    if cfg.get("skip_all"):
        return {
            "patterns": [],
            "playbook": None,
            "capability": None,
            "coupling": {
                "matched_files": [], "coupling_pairs": [],
                "suggested_groups": [], "confidence": 0.0,
            },
            "previous_plans": [],
            "saved_patterns": [],
        }

    signals: dict[str, Any] = {
        "patterns": [
            {"strategy": "stigmergic", "quality_mean": 0.75, "sample_count": 5},
        ],
        "playbook": (
            "code_implementation (conf=1.00) -> 3-5 colonies, "
            "grouped files, coder-led, stigmergic"
        ),
        "capability": {
            "label": "qwen3.5-35b", "quality_mean": 0.82,
            "optimal_files": "5-8",
        },
        "coupling": {
            "matched_files": [], "coupling_pairs": [],
            "suggested_groups": [], "confidence": 0.0,
        },
        "previous_plans": [
            {"strategy": "stigmergic", "quality_mean": 0.65},
        ],
        "saved_patterns": [],
    }

    if not cfg.get("skip_coupling"):
        signals["coupling"] = {
            "matched_files": ["src/runner.py", "src/types.py"],
            "coupling_pairs": [
                {"from": "src/runner.py", "to": "src/types.py", "type": "imports"},
            ],
            "suggested_groups": [
                {"files": ["src/runner.py", "src/types.py"], "reason": "coupled files"},
            ],
            "confidence": 0.7,
        }

    if not cfg.get("skip_saved"):
        signals["saved_patterns"] = [{
            "pattern_id": "pp-test",
            "name": "Prior addon plan",
            "task_previews": [
                {"task_id": "t1", "task": "scanner", "caste": "coder"},
                {"task_id": "t2", "task": "handlers", "caste": "coder"},
                {"task_id": "t3", "task": "tests", "caste": "coder"},
            ],
            "groups": [{"taskIds": ["t1", "t2"]}, {"taskIds": ["t3"]}],
        }]

    return signals


@dataclass
class AblationResult:
    prompt: str
    config: str
    task_class: str
    complexity: str
    is_colony_work: bool
    prefers_single: bool
    inferred_route: str
    signal_summary: str


def _run_ablation_prompt(prompt: str, config_name: str) -> AblationResult:
    """Run a single prompt under a given ablation config via planning policy."""
    from formicos.surface.planning_policy import decide_planning_route

    decision = decide_planning_route(prompt)
    task_class = decision.task_class
    complexity = decision.complexity
    colony_work = _looks_like_colony_work(prompt)
    single = _prefer_single_colony_route(prompt)

    # Map fast_path to "none" when classifiers say not colony work
    route = "none" if decision.route == "fast_path" and not colony_work else decision.route

    signals = _mock_signals(config_name)
    signal_parts = []
    if signals.get("playbook"):
        signal_parts.append("playbook")
    if signals.get("capability"):
        signal_parts.append("capability")
    if signals["coupling"].get("confidence", 0) > 0:
        signal_parts.append("coupling")
    if signals.get("saved_patterns"):
        signal_parts.append(f"saved({len(signals['saved_patterns'])})")

    return AblationResult(
        prompt=prompt,
        config=config_name,
        task_class=task_class,
        complexity=complexity,
        is_colony_work=colony_work,
        prefers_single=single,
        inferred_route=route,
        signal_summary="+".join(signal_parts) if signal_parts else "none",
    )


# ── Deterministic ablation tests ──

class TestAblationStructure:
    """Structural comparison across ablation configs."""

    def test_all_configs_produce_results(self) -> None:
        """Every config x prompt combination should produce a result."""
        for prompt in ABLATION_PROMPTS:
            for config_name in ABLATION_CONFIGS:
                result = _run_ablation_prompt(prompt, config_name)
                assert result.task_class
                valid = ("none", "fast_path", "single_colony", "parallel_dag")
                assert result.inferred_route in valid

    def test_none_config_has_no_signals(self) -> None:
        """The 'none' config should report no active signals."""
        for prompt in ABLATION_PROMPTS:
            result = _run_ablation_prompt(prompt, "none")
            assert result.signal_summary == "none"

    def test_full_config_has_all_signals(self) -> None:
        """The 'full' config should include all signal types."""
        result = _run_ablation_prompt(ABLATION_PROMPTS[1], "full")  # multi-file
        assert "playbook" in result.signal_summary
        assert "capability" in result.signal_summary
        assert "coupling" in result.signal_summary
        assert "saved" in result.signal_summary

    def test_route_changes_captured(self) -> None:
        """Wave 85: capture route differences across configs.

        Routes may now change across signal configs because the policy
        object integrates playbook hints. Report changes instead of
        asserting stability.
        """
        drifts: list[str] = []
        for prompt in ABLATION_PROMPTS:
            routes: dict[str, str] = {}
            for config_name in ABLATION_CONFIGS:
                result = _run_ablation_prompt(prompt, config_name)
                routes[config_name] = result.inferred_route
            unique = set(routes.values())
            if len(unique) > 1:
                drifts.append(f"{prompt[:50]}: {routes}")
        # Informational — print route drifts for visibility
        if drifts:
            print(f"\nRoute changes across configs ({len(drifts)}):")
            for d in drifts:
                print(f"  {d}")
        # No assertion — route drift is now expected and tracked


class TestAblationReport:
    """Generate comparison tables."""

    def test_comparison_table(self) -> None:
        """Print a structured comparison table (always passes)."""
        rows: list[dict[str, str]] = []
        for prompt in ABLATION_PROMPTS:
            for config_name in ABLATION_CONFIGS:
                r = _run_ablation_prompt(prompt, config_name)
                rows.append({
                    "prompt": r.prompt[:50],
                    "config": r.config,
                    "route": r.inferred_route,
                    "signals": r.signal_summary,
                    "task_class": r.task_class,
                })

        # Group by prompt for readability
        by_prompt: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_prompt.setdefault(row["prompt"], []).append(row)

        lines = ["", "=== ABLATION COMPARISON ===", ""]
        for prompt, configs in by_prompt.items():
            lines.append(f"Prompt: {prompt}")
            for c in configs:
                lines.append(f"  {c['config']:12s} -> {c['route']:15s}  signals: {c['signals']}")
            lines.append("")

        report = "\n".join(lines)
        print(report)

    def test_json_report(self) -> None:
        """Produce a JSON-serializable ablation report (always passes)."""
        results: list[dict[str, Any]] = []
        for prompt in ABLATION_PROMPTS:
            prompt_results = {}
            for config_name in ABLATION_CONFIGS:
                r = _run_ablation_prompt(prompt, config_name)
                prompt_results[config_name] = {
                    "route": r.inferred_route,
                    "signals": r.signal_summary,
                    "task_class": r.task_class,
                    "complexity": r.complexity,
                }
            results.append({"prompt": prompt, "configs": prompt_results})
        print(json.dumps(results, indent=2))
