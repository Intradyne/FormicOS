"""Markdown comparison report generator for evaluation results.

Usage::

    python -m formicos.eval.compare --task email-validator
    python -m formicos.eval.compare --task all
    python -m formicos.eval.compare --task email-validator --data-dir ./data

Reads JSON result files from ``{data_dir}/eval/results/{task_id}/`` and
produces a markdown comparison report at ``{data_dir}/eval/reports/{task_id}.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path("./data")


# ---------------------------------------------------------------------------
# Result loading
# ---------------------------------------------------------------------------


def _load_results(task_id: str, data_dir: Path) -> list[dict[str, Any]]:
    """Load all JSON result files for a given task."""
    results_dir = data_dir / "eval" / "results" / task_id
    if not results_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as fh:
            results.append(json.load(fh))
    return results


def _list_evaluated_tasks(data_dir: Path) -> list[str]:
    """Return task ids that have result files."""
    results_base = data_dir / "eval" / "results"
    if not results_base.exists():
        return []
    return sorted(
        d.name
        for d in results_base.iterdir()
        if d.is_dir() and any(d.glob("*.json"))
    )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _group_by_strategy(
    results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group results by strategy name."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        strategy = r.get("strategy", "unknown")
        grouped.setdefault(strategy, []).append(r)
    return grouped


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics for a list of runs."""
    return {
        "count": len(runs),
        "avg_quality": _avg([r.get("quality_score", 0.0) for r in runs]),
        "avg_cost": _avg([r.get("cost", 0.0) for r in runs]),
        "avg_wall_time_s": _avg([r.get("wall_time_s", 0.0) for r in runs]),
        "avg_rounds": _avg([float(r.get("rounds_completed", 0)) for r in runs]),
        "completion_rate": (
            round(
                sum(1 for r in runs if r.get("status") == "completed") / len(runs),
                2,
            )
            if runs
            else 0.0
        ),
        "total_redirects": sum(
            len(r.get("redirect_history", [])) for r in runs
        ),
        "total_skills": sum(r.get("skills_extracted", 0) for r in runs),
        "total_knowledge_used": sum(
            len(r.get("knowledge_used", [])) for r in runs
        ),
    }


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _generate_report(
    task_id: str,
    results: list[dict[str, Any]],
) -> str:
    """Generate a markdown comparison report."""
    grouped = _group_by_strategy(results)
    summaries = {s: _summarize(runs) for s, runs in grouped.items()}
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Extract held-constant variables from first result
    first = results[0] if results else {}
    team_desc = ""
    for member in first.get("team", []):
        team_desc += (
            f"  - {member.get('caste', '?')} "
            f"(tier={member.get('tier', '?')}, "
            f"count={member.get('count', '?')}, "
            f"model={member.get('model', '?')})\n"
        )

    lines: list[str] = []
    lines.append(f"# Evaluation Report: {task_id}")
    lines.append("")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Task:** {task_id}  ")
    lines.append(f"**Total runs:** {len(results)}")
    lines.append("")

    # Disclaimer
    lines.append("> **Exploratory results only.** These comparisons are based on a")
    lines.append("> small number of runs and should NOT be treated as statistically")
    lines.append("> significant. They are intended to surface qualitative patterns")
    lines.append("> and inform further investigation, not to prove claims.")
    lines.append("")

    # Task description
    task_desc = first.get("transcript", {}).get("original_task", "")
    if task_desc:
        lines.append("## Task Description")
        lines.append("")
        lines.append(f"> {task_desc[:500]}")
        lines.append("")

    # Variables held constant
    lines.append("## Variables Held Constant")
    lines.append("")
    if team_desc:
        lines.append(f"- **Team composition:**\n{team_desc}")
    budget = first.get("transcript", {}).get("budget_limit", "n/a")
    if budget == "n/a":
        # Try from result directly
        budget = "see task YAML"
    lines.append(f"- **Budget limit:** {budget}")
    lines.append("- **Model assignments:** from system config cascade")
    lines.append("")

    # Summary comparison table
    lines.append("## Summary Comparison")
    lines.append("")
    headers = [
        "Metric",
        *list(summaries.keys()),
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    metrics = [
        ("Runs", "count"),
        ("Avg Quality", "avg_quality"),
        ("Avg Cost ($)", "avg_cost"),
        ("Avg Wall Time (s)", "avg_wall_time_s"),
        ("Avg Rounds", "avg_rounds"),
        ("Completion Rate", "completion_rate"),
        ("Total Redirects", "total_redirects"),
        ("Total Skills Extracted", "total_skills"),
        ("Total Knowledge Used", "total_knowledge_used"),
    ]
    for label, key in metrics:
        row = [label]
        for strategy in summaries:
            val = summaries[strategy].get(key, "n/a")
            row.append(str(val))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Per-run detail table
    lines.append("## Per-Run Details")
    lines.append("")
    lines.append(
        "| Run | Strategy | Status | Quality | Cost ($) | "
        "Wall Time (s) | Rounds | Colony ID |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(results, key=lambda x: (x.get("strategy", ""), x.get("run_index", 0))):
        lines.append(
            f"| {r.get('run_index', 0)} "
            f"| {r.get('strategy', '?')} "
            f"| {r.get('status', '?')} "
            f"| {r.get('quality_score', 0.0)} "
            f"| {r.get('cost', 0.0):.4f} "
            f"| {r.get('wall_time_s', 0.0)} "
            f"| {r.get('rounds_completed', 0)} "
            f"| `{r.get('colony_id', '?')}` |"
        )
    lines.append("")

    # Redirect and skill carry-forward evidence
    any_redirects = any(r.get("redirect_history") for r in results)
    any_skills = any(r.get("skills_extracted", 0) > 0 for r in results)
    any_inputs = any(r.get("input_sources") for r in results)

    if any_redirects or any_skills or any_inputs:
        lines.append("## Coordination Evidence")
        lines.append("")
        if any_redirects:
            lines.append("### Redirects")
            lines.append("")
            for r in results:
                rh = r.get("redirect_history", [])
                if rh:
                    lines.append(
                        f"- **{r.get('strategy')} run {r.get('run_index', 0)}** "
                        f"({r.get('colony_id', '?')}): "
                        f"{len(rh)} redirect(s)"
                    )
            lines.append("")
        if any_skills:
            lines.append("### Skills Extracted")
            lines.append("")
            for r in results:
                sk = r.get("skills_extracted", 0)
                if sk > 0:
                    lines.append(
                        f"- **{r.get('strategy')} run {r.get('run_index', 0)}**: "
                        f"{sk} skill(s)"
                    )
            lines.append("")
        if any_inputs:
            lines.append("### Input Sources (Skill Carry-Forward)")
            lines.append("")
            for r in results:
                ins = r.get("input_sources", [])
                if ins:
                    lines.append(
                        f"- **{r.get('strategy')} run {r.get('run_index', 0)}**: "
                        f"{len(ins)} input source(s)"
                    )
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*Report generated by `formicos.eval.compare`. "
        "These results are exploratory and not statistically significant.*"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_report(
    task_id: str,
    data_dir: Path | None = None,
) -> Path | None:
    """Generate a comparison report for a task. Returns the report path."""
    dd = data_dir or _DEFAULT_DATA_DIR

    task_ids = _list_evaluated_tasks(dd) if task_id == "all" else [task_id]

    if not task_ids:
        print(f"No results found in {dd / 'eval' / 'results'}")  # noqa: T201
        return None

    reports_dir = dd / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    last_path: Path | None = None

    for tid in task_ids:
        results = _load_results(tid, dd)
        if not results:
            print(f"  No results for task '{tid}', skipping.")  # noqa: T201
            continue

        report = _generate_report(tid, results)
        path = reports_dir / f"{tid}.md"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"  Report: {path}")  # noqa: T201
        last_path = path

    return last_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formicos.eval.compare",
        description="Generate markdown comparison reports from evaluation results.",
    )
    parser.add_argument(
        "--task",
        default=None,
        help='Task id (or "all" for every evaluated task).',
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (default: ./data).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List tasks with available results and exit.",
    )

    args = parser.parse_args()
    dd = Path(args.data_dir) if args.data_dir else _DEFAULT_DATA_DIR

    if args.list:
        for tid in _list_evaluated_tasks(dd):
            results = _load_results(tid, dd)
            print(f"  {tid:<25} {len(results)} result(s)")  # noqa: T201
        sys.exit(0)

    if args.task is None:
        parser.error("--task is required (or use --list to see evaluated tasks)")

    generate_report(task_id=args.task, data_dir=dd)


if __name__ == "__main__":
    main()
