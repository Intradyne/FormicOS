"""Wave 41 B3: Compounding-curve report generator.

Takes sequential run results and produces three curve views:
  1. Raw performance: quality_score over task sequence
  2. Cost-normalized: quality_score / cost over task sequence
  3. Time-normalized: quality_score / wall_time_s over task sequence

Also tracks knowledge contribution: which earlier-extracted knowledge
was accessed by later tasks.

Usage::

    python -m formicos.eval.compounding_curve --suite default
    python -m formicos.eval.compounding_curve --suite default --data-dir ./data
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


def _load_sequential_results(
    suite_id: str, data_dir: Path,
) -> list[dict[str, Any]]:
    """Load all sequential run result files for a suite."""
    results_dir = data_dir / "eval" / "sequential" / suite_id
    if not results_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("run_*.json")):
        with path.open("r", encoding="utf-8") as fh:
            results.append(json.load(fh))
    return results


def _list_suites_with_results(data_dir: Path) -> list[str]:
    """Return suite ids that have sequential results."""
    base = data_dir / "eval" / "sequential"
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and any(d.glob("run_*.json"))
    )


# ---------------------------------------------------------------------------
# Curve computation
# ---------------------------------------------------------------------------


def compute_curves(run: dict[str, Any]) -> dict[str, Any]:
    """Compute the three compounding curves from a sequential run result.

    Returns a dict with:
      - raw_curve: list of {task_id, seq, quality_score}
      - cost_curve: list of {task_id, seq, quality_per_dollar}
      - time_curve: list of {task_id, seq, quality_per_second}
      - cumulative: list of {task_id, seq, cum_quality, cum_cost, cum_time,
                             cum_entries_extracted, cum_entries_accessed}
      - knowledge_contribution: {total_extracted, total_accessed,
                                  access_ratio, extraction_by_task}
    """
    tasks: list[dict[str, Any]] = run.get("tasks", [])
    if not tasks:
        return {
            "raw_curve": [],
            "cost_curve": [],
            "time_curve": [],
            "cumulative": [],
            "knowledge_contribution": {},
        }

    raw_curve: list[dict[str, Any]] = []
    cost_curve: list[dict[str, Any]] = []
    time_curve: list[dict[str, Any]] = []
    cumulative: list[dict[str, Any]] = []

    cum_quality = 0.0
    cum_cost = 0.0
    cum_time = 0.0
    cum_extracted = 0
    cum_accessed = 0
    extraction_by_task: list[dict[str, Any]] = []

    for t in tasks:
        seq = t.get("sequence_index", 0)
        task_id = t.get("task_id", "")
        quality = float(t.get("quality_score", 0.0))
        cost = float(t.get("cost", 0.0))
        wall_time = float(t.get("wall_time_s", 0.0))
        extracted = int(t.get("entries_extracted", 0))
        accessed = int(t.get("entries_accessed", 0))

        raw_curve.append({
            "task_id": task_id,
            "seq": seq,
            "quality_score": quality,
        })

        # Cost-normalized: quality per dollar (avoid division by zero)
        quality_per_dollar = quality / cost if cost > 0 else 0.0
        cost_curve.append({
            "task_id": task_id,
            "seq": seq,
            "quality_per_dollar": round(quality_per_dollar, 4),
        })

        # Time-normalized: quality per second
        quality_per_second = quality / wall_time if wall_time > 0 else 0.0
        time_curve.append({
            "task_id": task_id,
            "seq": seq,
            "quality_per_second": round(quality_per_second, 6),
        })

        cum_quality += quality
        cum_cost += cost
        cum_time += wall_time
        cum_extracted += extracted
        cum_accessed += accessed

        cumulative.append({
            "task_id": task_id,
            "seq": seq,
            "cum_quality": round(cum_quality, 4),
            "cum_cost": round(cum_cost, 4),
            "cum_time": round(cum_time, 2),
            "cum_entries_extracted": cum_extracted,
            "cum_entries_accessed": cum_accessed,
        })

        extraction_by_task.append({
            "task_id": task_id,
            "seq": seq,
            "entries_extracted": extracted,
            "entries_accessed": accessed,
        })

    # Knowledge contribution summary
    total_extracted = sum(t.get("entries_extracted", 0) for t in tasks)
    total_accessed = sum(t.get("entries_accessed", 0) for t in tasks)
    access_ratio = total_accessed / total_extracted if total_extracted > 0 else 0.0

    # Attribution from structured knowledge_attribution if present
    total_used_ids = sum(
        len(t.get("knowledge_attribution", {}).get("used_ids", []))
        for t in tasks
    )
    total_produced_ids = sum(
        len(t.get("knowledge_attribution", {}).get("produced_ids", []))
        for t in tasks
    )

    return {
        "raw_curve": raw_curve,
        "cost_curve": cost_curve,
        "time_curve": time_curve,
        "cumulative": cumulative,
        "knowledge_contribution": {
            "total_extracted": total_extracted,
            "total_accessed": total_accessed,
            "access_ratio": round(access_ratio, 2),
            "total_knowledge_used": total_used_ids,
            "total_knowledge_produced": total_produced_ids,
            "extraction_by_task": extraction_by_task,
        },
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _trend_indicator(values: list[float]) -> str:
    """Simple trend indicator: rising, flat, or declining."""
    if len(values) < 2:
        return "insufficient data"
    first_half = values[: len(values) // 2]
    second_half = values[len(values) // 2 :]
    if not first_half or not second_half:
        return "insufficient data"
    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)
    if avg_first == 0:
        return "from zero baseline"
    change = (avg_second - avg_first) / avg_first
    if change > 0.10:
        return f"rising (+{change:.0%})"
    if change < -0.10:
        return f"declining ({change:.0%})"
    return f"flat ({change:+.0%})"


def generate_curve_report(
    suite_id: str,
    run: dict[str, Any],
    curves: dict[str, Any],
) -> str:
    """Generate a markdown compounding-curve report."""
    conditions = run.get("conditions", {})
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(f"# Compounding Curve Report: {suite_id}")
    lines.append("")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Suite:** {suite_id}  ")
    lines.append(f"**Tasks:** {len(run.get('tasks', []))}  ")
    lines.append(f"**Total cost:** ${run.get('total_cost', 0):.4f}  ")
    lines.append(f"**Total wall time:** {run.get('total_wall_time_s', 0):.1f}s")
    lines.append("")

    # Disclaimer
    lines.append("> **Exploratory measurement.** This report measures whether")
    lines.append("> accumulated knowledge improves later task performance.")
    lines.append("> Results are useful whether the curve rises or stays flat.")
    lines.append("> A flat curve is an honest finding, not a failure.")
    lines.append("")

    # Locked conditions
    lines.append("## Experiment Conditions (Locked)")
    lines.append("")
    lines.append(f"- **Strategy:** {conditions.get('strategy', 'n/a')}")
    lines.append(f"- **Budget per task:** ${conditions.get('budget_per_task', 0):.2f}")
    lines.append(f"- **Max rounds per task:** {conditions.get('max_rounds_per_task', 'n/a')}")
    lines.append(f"- **Escalation policy:** {conditions.get('escalation_policy', 'n/a')}")
    lines.append(f"- **Knowledge mode:** {conditions.get('knowledge_mode', 'accumulate')}")
    lines.append(f"- **Foraging policy:** {conditions.get('foraging_policy', 'disabled')}")
    lines.append(f"- **Config hash:** `{conditions.get('config_hash', 'n/a')}`")
    model_mix = conditions.get("model_mix", {})
    if model_mix:
        lines.append(f"- **Model mix:** {json.dumps(model_mix)}")
    else:
        lines.append("- **Model mix:** from system defaults")
    lines.append(f"- **Task order:** {' → '.join(conditions.get('task_order', []))}")
    lines.append("")

    # Raw performance curve
    raw = curves.get("raw_curve", [])
    if raw:
        quality_values = [p["quality_score"] for p in raw]
        lines.append("## 1. Raw Performance Curve")
        lines.append("")
        lines.append(f"**Trend:** {_trend_indicator(quality_values)}")
        lines.append("")
        lines.append("| Seq | Task | Quality |")
        lines.append("|-----|------|---------|")
        for p in raw:
            lines.append(f"| {p['seq']} | {p['task_id']} | {p['quality_score']:.4f} |")
        lines.append("")

    # Cost-normalized curve
    cost_c = curves.get("cost_curve", [])
    if cost_c:
        qpd_values = [p["quality_per_dollar"] for p in cost_c]
        lines.append("## 2. Cost-Normalized Curve (Quality / $)")
        lines.append("")
        lines.append(f"**Trend:** {_trend_indicator(qpd_values)}")
        lines.append("")
        lines.append("| Seq | Task | Quality/$ |")
        lines.append("|-----|------|-----------|")
        for p in cost_c:
            lines.append(f"| {p['seq']} | {p['task_id']} | {p['quality_per_dollar']:.4f} |")
        lines.append("")

    # Time-normalized curve
    time_c = curves.get("time_curve", [])
    if time_c:
        qps_values = [p["quality_per_second"] for p in time_c]
        lines.append("## 3. Time-Normalized Curve (Quality / second)")
        lines.append("")
        lines.append(f"**Trend:** {_trend_indicator(qps_values)}")
        lines.append("")
        lines.append("| Seq | Task | Quality/s |")
        lines.append("|-----|------|-----------|")
        for p in time_c:
            lines.append(f"| {p['seq']} | {p['task_id']} | {p['quality_per_second']:.6f} |")
        lines.append("")

    # Knowledge contribution
    kc = curves.get("knowledge_contribution", {})
    if kc:
        lines.append("## 4. Knowledge Contribution")
        lines.append("")
        lines.append(f"- **Total entries extracted:** {kc.get('total_extracted', 0)}")
        lines.append(f"- **Total entries accessed:** {kc.get('total_accessed', 0)}")
        lines.append(f"- **Access ratio:** {kc.get('access_ratio', 0):.2f} (accessed/extracted)")
        if kc.get("total_knowledge_used", 0) > 0:
            lines.append(f"- **Attributed knowledge used:** {kc['total_knowledge_used']}")
            lines.append(f"- **Knowledge produced:** {kc.get('total_knowledge_produced', 0)}")
        lines.append("")
        ext_by_task = kc.get("extraction_by_task", [])
        if ext_by_task:
            lines.append("| Seq | Task | Extracted | Accessed |")
            lines.append("|-----|------|-----------|----------|")
            for e in ext_by_task:
                lines.append(
                    f"| {e['seq']} | {e['task_id']} "
                    f"| {e['entries_extracted']} "
                    f"| {e['entries_accessed']} |"
                )
            lines.append("")

    # Cumulative view
    cum = curves.get("cumulative", [])
    if cum:
        lines.append("## 5. Cumulative View")
        lines.append("")
        lines.append(
            "| Seq | Task | Cum Quality | Cum Cost "
            "| Cum Time | Cum Extracted | Cum Accessed |"
        )
        lines.append(
            "|-----|------|-------------|----------"
            "|----------|---------------|--------------|"
        )
        for c in cum:
            lines.append(
                f"| {c['seq']} | {c['task_id']} "
                f"| {c['cum_quality']:.4f} "
                f"| ${c['cum_cost']:.4f} "
                f"| {c['cum_time']:.1f}s "
                f"| {c['cum_entries_extracted']} "
                f"| {c['cum_entries_accessed']} |"
            )
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*Report generated by `formicos.eval.compounding_curve`. "
        "These results are exploratory. A flat curve is an honest "
        "finding — it means the knowledge system is not yet "
        "improving later work under these conditions.*"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_compounding_report(
    suite_id: str,
    data_dir: Path | None = None,
    run_index: int = -1,
) -> Path | None:
    """Generate a compounding-curve report for a suite.

    Parameters
    ----------
    suite_id:
        Suite to report on.
    data_dir:
        Data directory containing eval results.
    run_index:
        Which run to report (-1 = latest).

    Returns
    -------
    Path to the generated report, or None if no results.
    """
    dd = data_dir or _DEFAULT_DATA_DIR

    suite_ids = (
        _list_suites_with_results(dd) if suite_id == "all" else [suite_id]
    )

    if not suite_ids:
        print(f"No sequential results found in {dd / 'eval' / 'sequential'}")  # noqa: T201
        return None

    reports_dir = dd / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    last_path: Path | None = None

    for sid in suite_ids:
        runs = _load_sequential_results(sid, dd)
        if not runs:
            print(f"  No results for suite '{sid}', skipping.")  # noqa: T201
            continue

        run = runs[run_index] if abs(run_index) <= len(runs) else runs[-1]
        curves = compute_curves(run)
        report = generate_curve_report(sid, run, curves)

        path = reports_dir / f"compounding_{sid}.md"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"  Report: {path}")  # noqa: T201

        # Also save raw curve data as JSON
        curves_path = reports_dir / f"compounding_{sid}_data.json"
        with curves_path.open("w", encoding="utf-8") as fh:
            json.dump(curves, fh, indent=2)
        print(f"  Curve data: {curves_path}")  # noqa: T201

        last_path = path

    return last_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formicos.eval.compounding_curve",
        description="Generate compounding-curve reports from sequential run results.",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help='Suite id (or "all" for every suite with results).',
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (default: ./data).",
    )
    parser.add_argument(
        "--run",
        type=int,
        default=-1,
        help="Run index within the suite (-1 = latest).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List suites with results and exit.",
    )

    args = parser.parse_args()
    dd = Path(args.data_dir) if args.data_dir else _DEFAULT_DATA_DIR

    if args.list:
        for sid in _list_suites_with_results(dd):
            runs = _load_sequential_results(sid, dd)
            print(f"  {sid:<25} {len(runs)} run(s)")  # noqa: T201
        sys.exit(0)

    if args.suite is None:
        parser.error("--suite is required (or use --list)")

    generate_compounding_report(
        suite_id=args.suite,
        data_dir=dd,
        run_index=args.run,
    )


if __name__ == "__main__":
    main()
