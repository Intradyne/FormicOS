"""Wave 41 B3: Sequential task runner with locked experiment conditions.

Runs a sequence of tasks measuring the compounding curve: does later work
benefit from earlier accumulated knowledge?

Usage::

    python -m formicos.eval.sequential_runner --suite default --config config/formicos.yaml
    python -m formicos.eval.sequential_runner --list-suites

The runner locks experiment conditions (model mix, budget, escalation
policy, task ordering) and records them alongside results so that
reported curves cannot be dismissed as policy drift.

Knowledge modes (behaviorally enforced):
  - ``accumulate``: single workspace for the whole run, knowledge carries forward
  - ``empty``: fresh workspace per task, no knowledge carry-over

Foraging policy: only ``disabled`` is supported. The eval harness cannot
reliably enforce reactive/proactive foraging from within the eval layer.

Results are saved to ``{data_dir}/eval/sequential/{suite_id}/``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger()

_DEFAULT_SUITES_DIR = Path(__file__).resolve().parents[3] / "config" / "eval" / "suites"
_DEFAULT_TASKS_DIR = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"

_POLL_INTERVAL_S = 1.0
_POLL_TIMEOUT_S = 900.0  # Wave 56.5: 3-agent heavy tasks need ~600-750s on local inference

# Supported modes — anything else is rejected to stay honest
_SUPPORTED_KNOWLEDGE_MODES = ("accumulate", "empty")
_SUPPORTED_FORAGING_POLICIES = ("disabled",)


def _validate_modes(knowledge_mode: str, foraging_policy: str) -> None:
    """Fail fast if an unsupported mode is requested."""
    if knowledge_mode not in _SUPPORTED_KNOWLEDGE_MODES:
        raise ValueError(
            f"knowledge_mode={knowledge_mode!r} is not supported. "
            f"Supported: {_SUPPORTED_KNOWLEDGE_MODES}. "
            "'snapshot' was rejected because the eval harness cannot "
            "implement real snapshot semantics without product-core changes."
        )
    if foraging_policy not in _SUPPORTED_FORAGING_POLICIES:
        raise ValueError(
            f"foraging_policy={foraging_policy!r} is not supported. "
            f"Supported: {_SUPPORTED_FORAGING_POLICIES}. "
            "The eval harness cannot reliably enforce reactive/proactive "
            "foraging from within the eval layer."
        )


# ---------------------------------------------------------------------------
# Experiment condition recording
# ---------------------------------------------------------------------------


@dataclass
class ExperimentConditions:
    """Locked conditions for a sequential experiment run.

    Every reported curve must be accompanied by these conditions so that
    outsiders can judge whether drift explains the result.
    """

    suite_id: str
    task_order: list[str]
    strategy: str
    model_mix: dict[str, str]  # caste -> model address
    budget_per_task: float
    max_rounds_per_task: int
    escalation_policy: str  # "none" | "capability" | "fallback"
    knowledge_mode: str = "accumulate"  # "accumulate" | "empty" | "snapshot"
    foraging_policy: str = "disabled"  # "disabled" | "reactive" | "proactive"
    random_seed: int | None = None
    run_id: str = ""
    workspace_id: str = ""
    started_at: str = ""
    config_hash: str = ""  # SHA256 of relevant config sections
    git_commit: str = ""  # short SHA of HEAD at run time
    task_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeAttribution:
    """Structured attribution for knowledge used/produced by a task."""

    used: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {"id": str, "title": str, "source_task": str|None, "source_colony": str|None}
    produced: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {"id": str, "title": str, "category": str, "sub_type": str}
    used_ids: list[str] = field(default_factory=list)  # flat ID list for compat
    produced_ids: list[str] = field(default_factory=list)  # flat ID list for compat


@dataclass
class TaskResult:
    """Result of a single task within a sequential run."""

    task_id: str
    sequence_index: int
    colony_id: str
    status: str
    quality_score: float
    cost: float
    wall_time_s: float
    rounds_completed: int
    entries_extracted: int
    entries_accessed: int
    knowledge_used: list[str]  # IDs of knowledge entries retrieved (compat)
    skills_extracted: int
    knowledge_attribution: KnowledgeAttribution = field(
        default_factory=KnowledgeAttribution,
    )
    timestamp: str = ""
    # Wave 57 Sub-packet C: productivity breakdown
    rounds_productive: list[bool] = field(default_factory=list)
    total_productive_calls: int = 0
    total_observation_calls: int = 0


@dataclass
class SequentialRunResult:
    """Complete result of a sequential experiment run."""

    conditions: ExperimentConditions
    tasks: list[TaskResult] = field(default_factory=lambda: list[TaskResult]())
    total_cost: float = 0.0
    total_wall_time_s: float = 0.0
    completed_at: str = ""
    manifest_path: str = ""  # path to the run manifest file


# ---------------------------------------------------------------------------
# Suite loading
# ---------------------------------------------------------------------------


def load_suite(suite_id: str, suites_dir: Path | None = None) -> dict[str, Any]:
    """Load a suite definition YAML."""
    base = suites_dir or _DEFAULT_SUITES_DIR
    path = base / f"{suite_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Suite file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def list_suites(suites_dir: Path | None = None) -> list[str]:
    """Return sorted list of available suite ids."""
    base = suites_dir or _DEFAULT_SUITES_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def _config_hash(
    config_path: Path,
    suite: dict[str, Any],
    task_payloads: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Hash relevant config sections for drift detection."""
    content = ""
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            content = fh.read()
    combined = content + json.dumps(suite, sort_keys=True, default=str)
    if task_payloads:
        combined += json.dumps(task_payloads, sort_keys=True, default=str)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _resolve_task_profile(
    task: dict[str, Any],
    suite: dict[str, Any],
    suite_model_mix: dict[str, str],
) -> dict[str, Any]:
    """Return the effective colony shape for a task within a suite."""
    profile: dict[str, Any] = {
        "castes": task["castes"],
        "strategy": str(task.get("strategy", suite.get("strategy", "stigmergic"))),
        "budget_limit": float(task.get("budget_limit", suite.get("budget_per_task", 2.0))),
        "max_rounds": int(task.get("max_rounds", suite.get("max_rounds_per_task", 10))),
        "fast_path": bool(task.get("fast_path", False)),
        "model_mix": dict(suite_model_mix) | dict(task.get("model_mix", {})),
    }
    # Wave 57 Sub-packet B: per-task eval timeout override
    if "eval_timeout_s" in task:
        profile["eval_timeout_s"] = float(task["eval_timeout_s"])
    return profile


def _task_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    """Compress a task profile into a stable, serializable run-condition record."""
    return {
        "castes": profile["castes"],
        "strategy": profile["strategy"],
        "budget_limit": profile["budget_limit"],
        "max_rounds": profile["max_rounds"],
        "fast_path": profile["fast_path"],
        "model_mix": profile["model_mix"],
    }


def _git_short_sha() -> str:
    """Return short git SHA of HEAD, or empty string if not in a repo."""
    try:
        result = subprocess.run(  # noqa: S603, S607
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _write_manifest(
    result: SequentialRunResult,
    manifest_path: Path,
) -> None:
    """Write a run manifest beside the result file."""
    manifest = {
        "run_id": result.conditions.run_id,
        "suite_id": result.conditions.suite_id,
        "started_at": result.conditions.started_at,
        "completed_at": result.completed_at,
        "git_commit": result.conditions.git_commit,
        "config_hash": result.conditions.config_hash,
        "knowledge_mode": result.conditions.knowledge_mode,
        "foraging_policy": result.conditions.foraging_policy,
        "strategy": result.conditions.strategy,
        "workspace_id": result.conditions.workspace_id,
        "tasks_run": len(result.tasks),
        "total_cost": result.total_cost,
        "total_wall_time_s": result.total_wall_time_s,
        "task_ids": [t.task_id for t in result.tasks],
        "statuses": [t.status for t in result.tasks],
        "total_knowledge_used": sum(
            len(t.knowledge_attribution.used_ids) for t in result.tasks
        ),
        "total_knowledge_produced": sum(
            len(t.knowledge_attribution.produced_ids) for t in result.tasks
        ),
    }
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)


def _append_partial_result(
    partial_path: Path,
    task_result: TaskResult,
) -> None:
    """Append one completed task result to a JSONL recovery file."""
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    with partial_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(task_result), default=str))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Sequential runner core
# ---------------------------------------------------------------------------


_GOVERNANCE_EXTENSION_S = 300.0  # Wave 57: extra time for productive colonies
_IDLE_TIMEOUT_S = 180.0  # Wave 57+: kill colonies with no activity for 3 min


async def _wait_for_colony(
    projections: Any,
    colony_id: str,
    timeout_s: float = _POLL_TIMEOUT_S,
) -> str:
    """Poll projection until colony reaches terminal status.

    Three timeout layers:
    1. **Idle watchdog**: if no colony activity (AgentTurn, CodeExecuted,
       RoundStarted) for ``_IDLE_TIMEOUT_S``, return immediately.  Catches
       mid-round hangs where the subprocess or LLM call never returns.
    2. **Proportional extension**: near deadline, if the colony just
       completed a productive round, extend by ``BASE * ratio``.
       Staleness-guarded (requires a *new* round since last extension).
    3. **Hard cap**: total wall-clock never exceeds 2× original timeout.
    """
    start = time.monotonic()
    deadline = start + timeout_s
    max_deadline = start + timeout_s * 2  # hard cap: never exceed 2× original
    last_extended_round_ts = 0.0  # monotonic ts when last extension was granted

    while time.monotonic() < deadline:
        colony = projections.get_colony(colony_id)
        if colony is not None and colony.status not in ("pending", "running"):
            return str(colony.status)

        # Idle watchdog: no colony activity for _IDLE_TIMEOUT_S → give up
        if colony is not None:
            last_act = getattr(colony, "last_activity_at", 0.0)
            if last_act > 0 and (time.monotonic() - last_act) > _IDLE_TIMEOUT_S:
                log.info(
                    "eval.idle_timeout",
                    colony_id=colony_id,
                    idle_s=round(time.monotonic() - last_act),
                )
                return "timeout"

        await asyncio.sleep(_POLL_INTERVAL_S)

        # Productivity-proportional extension near deadline
        if time.monotonic() >= deadline - _POLL_INTERVAL_S:
            # Re-fetch after sleep so the extension decision uses fresh state
            colony = projections.get_colony(colony_id)
            if colony is None or colony.status not in ("pending", "running"):
                continue  # next iteration returns terminal status
            gov = getattr(colony, "last_governance_action", "")
            ratio = getattr(colony, "last_round_productive_ratio", 0.0)
            round_ts = getattr(colony, "last_round_completed_at", 0.0)
            if (
                gov == "continue"
                and ratio > 0.1
                and round_ts > last_extended_round_ts
            ):
                extension = _GOVERNANCE_EXTENSION_S * ratio
                new_deadline = min(
                    time.monotonic() + extension, max_deadline,
                )
                if new_deadline > deadline + _POLL_INTERVAL_S:
                    deadline = new_deadline
                    last_extended_round_ts = round_ts
                    log.info(
                        "eval.proportional_extension",
                        colony_id=colony_id,
                        extension_s=round(extension),
                        productive_ratio=round(ratio, 2),
                        remaining_s=round(deadline - time.monotonic()),
                    )
                elif deadline >= max_deadline - _POLL_INTERVAL_S:
                    log.info(
                        "eval.extension_capped",
                        colony_id=colony_id,
                        elapsed_s=round(time.monotonic() - start),
                        max_s=round(timeout_s * 2),
                    )

    return "timeout"


def _build_attribution(
    colony_proj: Any,  # noqa: ANN401
    projections: Any,  # noqa: ANN401
    run_source_map: dict[str, dict[str, Any]] | None = None,
) -> KnowledgeAttribution:
    """Build structured knowledge attribution from projection truth.

    Uses the same access/production logic as transcript_view.py:
    - knowledge_used: entries accessed via knowledge_accesses on the colony
    - knowledge_produced: entries whose source_colony_id matches this colony

    The ``run_source_map`` enriches source_task attribution for entries
    produced earlier in the same run, without relying on product fields
    like ``source_task_id`` that may not exist.
    """
    attr = KnowledgeAttribution()
    if colony_proj is None:
        return attr

    source_map = run_source_map or {}
    colony_id = getattr(colony_proj, "colony_id", "")
    seen_ids: set[str] = set()

    # Knowledge used: from colony's knowledge_accesses (same as transcript_view)
    for access in getattr(colony_proj, "knowledge_accesses", []):
        for item in access.get("items", []):
            kid = item.get("id", "")
            if kid and kid not in seen_ids:
                seen_ids.add(kid)
                entry = projections.memory_entries.get(kid, {})
                # Prefer run-local source map over product entry fields
                run_src = source_map.get(kid, {})
                attr.used.append({
                    "id": kid,
                    "title": entry.get("title", ""),
                    "source_task": (
                        run_src.get("task_id")
                        or entry.get("source_task_id")
                    ),
                    "source_colony": (
                        run_src.get("colony_id")
                        or entry.get("source_colony_id")
                    ),
                    "source_seq": run_src.get("seq"),
                })
                attr.used_ids.append(kid)

    # Knowledge produced: entries created by this colony
    for eid, entry in projections.memory_entries.items():
        if entry.get("source_colony_id") == colony_id:
            attr.produced.append({
                "id": eid,
                "title": entry.get("title", ""),
                "category": entry.get("category", ""),
                "sub_type": entry.get("sub_type", ""),
            })
            attr.produced_ids.append(eid)

    return attr


async def run_sequential(
    suite_id: str,
    config_path: Path | None = None,
    castes_path: Path | None = None,
    suites_dir: Path | None = None,
    tasks_dir: Path | None = None,
    dry_run: bool = False,
    knowledge_mode: str = "accumulate",
    foraging_policy: str = "disabled",
) -> SequentialRunResult:
    """Run a sequential experiment: tasks executed in order.

    Parameters
    ----------
    suite_id:
        Suite definition to load (from config/eval/suites/).
    config_path:
        Path to formicos.yaml. Defaults to config/formicos.yaml.
    castes_path:
        Path to caste_recipes.yaml. Defaults to config/caste_recipes.yaml.
    dry_run:
        If True, validate conditions and return without executing.
    knowledge_mode:
        ``accumulate`` (shared workspace) or ``empty`` (fresh per task).
    foraging_policy:
        Only ``disabled`` is supported.

    Returns
    -------
    SequentialRunResult with all task results and locked conditions.
    """
    _validate_modes(knowledge_mode, foraging_policy)

    from formicos.eval.run import (
        _bootstrap,  # pyright: ignore[reportPrivateUsage]
        _load_task,  # pyright: ignore[reportPrivateUsage]
        _parse_castes,  # pyright: ignore[reportPrivateUsage]
    )

    project_root = Path(__file__).resolve().parents[3]
    cfg = config_path or project_root / "config" / "formicos.yaml"
    cst = castes_path or project_root / "config" / "caste_recipes.yaml"

    suite = load_suite(suite_id, suites_dir)
    task_ids: list[str] = suite["task_order"]
    strategy: str = suite.get("strategy", "stigmergic")
    budget: float = float(suite.get("budget_per_task", 2.0))
    max_rounds: int = int(suite.get("max_rounds_per_task", 10))
    escalation_policy: str = suite.get("escalation_policy", "none")
    model_mix: dict[str, str] = suite.get("model_mix", {})
    task_payloads = {
        task_id: _load_task(task_id, tasks_dir)
        for task_id in task_ids
    }
    task_profiles = {
        task_id: _resolve_task_profile(task_payloads[task_id], suite, model_mix)
        for task_id in task_ids
    }

    run_id = uuid.uuid4().hex[:12]

    conditions = ExperimentConditions(
        suite_id=suite_id,
        task_order=task_ids,
        strategy=strategy,
        model_mix=model_mix,
        budget_per_task=budget,
        max_rounds_per_task=max_rounds,
        escalation_policy=escalation_policy,
        knowledge_mode=knowledge_mode,
        foraging_policy=foraging_policy,
        run_id=run_id,
        started_at=datetime.now(UTC).isoformat(),
        config_hash=_config_hash(cfg, suite, task_payloads),
        git_commit=_git_short_sha(),
        task_profiles={
            task_id: _task_profile_summary(task_profiles[task_id])
            for task_id in task_ids
        },
    )

    result = SequentialRunResult(conditions=conditions)

    if dry_run:
        log.info(
            "sequential.dry_run",
            suite=suite_id,
            tasks=task_ids,
            conditions=conditions.to_dict(),
        )
        return result

    # Bootstrap runtime
    runtime, colony_manager, projections, data_dir = await _bootstrap(cfg, cst)

    # ── Workspace setup depends on knowledge_mode ──
    #
    # accumulate: single workspace for the whole run, knowledge carries
    # empty: fresh workspace per task, no carry-over
    base_ws_id = f"seq-{suite_id}-{run_id}"
    base_thread_id = f"seq-{suite_id}-{run_id}"
    conditions.workspace_id = base_ws_id

    if knowledge_mode == "accumulate":
        # One shared workspace for all tasks
        if projections.workspaces.get(base_ws_id) is None:
            await runtime.create_workspace(base_ws_id)
        if projections.get_thread(base_ws_id, base_thread_id) is None:
            await runtime.create_thread(base_ws_id, base_thread_id)

    results_dir = data_dir / "eval" / "sequential" / suite_id
    results_dir.mkdir(parents=True, exist_ok=True)
    partial_results_path = results_dir / "results.jsonl"
    partial_results_path.unlink(missing_ok=True)

    wall_start = time.monotonic()

    # Run-local source map: entry_id -> {task_id, seq, colony_id}
    # Built from produced entries of earlier tasks so later tasks can
    # get truthful source_task attribution without product-core fields.
    run_source_map: dict[str, dict[str, Any]] = {}

    for seq_idx, task_id in enumerate(task_ids):
        task = task_payloads[task_id]
        profile = task_profiles[task_id]
        task_wall_start = time.monotonic()

        try:
            castes = _parse_castes(profile["castes"])

            log.info(
                "sequential.task_start",
                suite=suite_id,
                task_id=task_id,
                sequence=seq_idx + 1,
                of=len(task_ids),
                knowledge_mode=knowledge_mode,
                strategy=profile["strategy"],
                fast_path=profile["fast_path"],
                max_rounds=profile["max_rounds"],
            )

            # ── Per-task workspace for empty mode ──
            if knowledge_mode == "empty":
                ws_id = f"seq-{suite_id}-{run_id}-t{seq_idx}"
                thread_id = f"seq-{suite_id}-{run_id}-t{seq_idx}"
                if projections.workspaces.get(ws_id) is None:
                    await runtime.create_workspace(ws_id)
                if projections.get_thread(ws_id, thread_id) is None:
                    await runtime.create_thread(ws_id, thread_id)
            else:
                ws_id = base_ws_id
                thread_id = base_thread_id

            colony_id = await runtime.spawn_colony(
                workspace_id=ws_id,
                thread_id=thread_id,
                task=task["description"],
                castes=castes,
                strategy=profile["strategy"],
                max_rounds=int(profile["max_rounds"]),
                budget_limit=float(profile["budget_limit"]),
                model_assignments=dict(profile["model_mix"]),
                fast_path=bool(profile["fast_path"]),
            )

            await colony_manager.start_colony(colony_id)
            # Wave 57: use per-task timeout if specified, else global default
            task_timeout = float(profile.get("eval_timeout_s", _POLL_TIMEOUT_S))
            status = await _wait_for_colony(projections, colony_id, timeout_s=task_timeout)

            # Wait for extraction to complete (fire-and-forget asyncio tasks
            # in _post_colony_hooks finish 3-12s after ColonyCompleted).
            # Poll projections.memory_extractions_completed (set of colony_ids).
            _EXTRACTION_TIMEOUT_S = 30.0
            _EXTRACTION_POLL_S = 1.0
            ext_deadline = time.monotonic() + _EXTRACTION_TIMEOUT_S
            while time.monotonic() < ext_deadline:
                if colony_id in projections.memory_extractions_completed:
                    break
                await asyncio.sleep(_EXTRACTION_POLL_S)
            else:
                log.warning(
                    "sequential.extraction_wait_timeout",
                    colony_id=colony_id,
                    task_id=task_id,
                )

            task_wall_time = round(time.monotonic() - task_wall_start, 2)

            # Collect transcript for metrics
            from formicos.surface.transcript import build_transcript

            colony_proj = projections.get_colony(colony_id)
            transcript: dict[str, Any] = {}
            if colony_proj is not None:
                transcript = build_transcript(colony_proj)

            # Build real knowledge attribution from projection truth,
            # enriched with run-local source-task map
            attribution = _build_attribution(
                colony_proj, projections, run_source_map,
            )
            entries_accessed = len(attribution.used_ids)

            # Update run-local source map with entries produced by this task
            for prod in attribution.produced:
                run_source_map[prod["id"]] = {
                    "task_id": task_id,
                    "seq": seq_idx,
                    "colony_id": colony_id,
                }

            # entries_extracted: use projection truth, not legacy transcript field
            entries_extracted_count = (
                getattr(colony_proj, "entries_extracted_count", 0)
                if colony_proj is not None
                else len(attribution.produced_ids)
            )

            # Wave 57 Sub-packet C: per-round productivity from projection
            rounds_productive: list[bool] = []
            total_prod = 0
            total_obs = 0
            if colony_proj is not None:
                total_prod = getattr(colony_proj, "productive_calls", 0)
                total_obs = getattr(colony_proj, "observation_calls", 0)
                _PROD_TOOLS = {
                    "write_workspace_file", "patch_file", "code_execute",
                    "workspace_execute", "git_commit",
                }
                for rec in getattr(colony_proj, "round_records", []):
                    all_tools: list[str] = []
                    for tools in rec.tool_calls.values():
                        all_tools.extend(tools)
                    rounds_productive.append(
                        any(t in _PROD_TOOLS for t in all_tools),
                    )

            task_result = TaskResult(
                task_id=task_id,
                sequence_index=seq_idx,
                colony_id=colony_id,
                status=status,
                quality_score=float(transcript.get("quality_score", 0.0)),
                cost=float(transcript.get("cost", 0.0)),
                wall_time_s=task_wall_time,
                rounds_completed=int(transcript.get("rounds_completed", 0)),
                entries_extracted=entries_extracted_count,
                entries_accessed=entries_accessed,
                knowledge_used=attribution.used_ids,
                skills_extracted=entries_extracted_count,
                knowledge_attribution=attribution,
                timestamp=datetime.now(UTC).isoformat(),
                rounds_productive=rounds_productive,
                total_productive_calls=total_prod,
                total_observation_calls=total_obs,
            )

        except Exception:  # noqa: BLE001
            log.exception(
                "sequential.task_error",
                task_id=task_id,
                sequence=seq_idx + 1,
            )
            task_result = TaskResult(
                task_id=task_id,
                sequence_index=seq_idx,
                colony_id="",
                status="error",
                quality_score=0.0,
                cost=0.0,
                wall_time_s=round(time.monotonic() - task_wall_start, 2),
                rounds_completed=0,
                entries_extracted=0,
                entries_accessed=0,
                knowledge_used=[],
                skills_extracted=0,
                knowledge_attribution=KnowledgeAttribution(),
                timestamp=datetime.now(UTC).isoformat(),
            )

        result.tasks.append(task_result)
        result.total_cost += task_result.cost
        _append_partial_result(partial_results_path, task_result)

        log.info(
            "sequential.task_complete",
            suite=suite_id,
            task_id=task_id,
            sequence=seq_idx + 1,
            status=task_result.status,
            quality=task_result.quality_score,
            cost=task_result.cost,
            rounds=task_result.rounds_completed,
            entries_extracted=task_result.entries_extracted,
            entries_accessed=task_result.entries_accessed,
        )

    result.total_wall_time_s = round(time.monotonic() - wall_start, 2)
    result.completed_at = datetime.now(UTC).isoformat()

    # Save full result with run_id in filename for uniqueness
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    result_path = results_dir / f"run_{ts}_{run_id}.json"
    with result_path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(result), fh, indent=2, default=str)

    # Write manifest beside the result
    manifest_path = results_dir / f"manifest_{ts}_{run_id}.json"
    _write_manifest(result, manifest_path)
    result.manifest_path = str(manifest_path)

    log.info(
        "sequential.complete",
        suite=suite_id,
        run_id=run_id,
        tasks_run=len(result.tasks),
        total_cost=result.total_cost,
        total_wall_time_s=result.total_wall_time_s,
        saved=str(result_path),
        manifest=str(manifest_path),
    )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formicos.eval.sequential_runner",
        description="Sequential task runner with locked experiment conditions.",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="Suite id to run (from config/eval/suites/).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to formicos.yaml.",
    )
    parser.add_argument(
        "--castes-config",
        default=None,
        help="Path to caste_recipes.yaml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate conditions without executing.",
    )
    parser.add_argument(
        "--knowledge-mode",
        default="accumulate",
        choices=list(_SUPPORTED_KNOWLEDGE_MODES),
        help="Knowledge isolation mode (default: accumulate).",
    )
    parser.add_argument(
        "--foraging-policy",
        default="disabled",
        choices=list(_SUPPORTED_FORAGING_POLICIES),
        help="Foraging policy for the run (default: disabled).",
    )
    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List available suites and exit.",
    )

    args = parser.parse_args()

    if args.list_suites:
        for sid in list_suites():
            suite = load_suite(sid)
            tasks = suite.get("task_order", [])
            print(f"  {sid:<25} {len(tasks)} tasks")  # noqa: T201
        sys.exit(0)

    if args.suite is None:
        parser.error("--suite is required (or use --list-suites)")

    config_path = Path(args.config) if args.config else None
    castes_path = Path(args.castes_config) if args.castes_config else None

    asyncio.run(run_sequential(
        suite_id=args.suite,
        config_path=config_path,
        castes_path=castes_path,
        dry_run=args.dry_run,
        knowledge_mode=args.knowledge_mode,
        foraging_policy=args.foraging_policy,
    ))


if __name__ == "__main__":
    main()
