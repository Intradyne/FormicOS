"""A/B evaluation harness — stigmergic vs sequential strategy comparison.

Usage::

    python -m formicos.eval.run --task email-validator --runs 3
    python -m formicos.eval.run --task all --runs 2
    python -m formicos.eval.run --list

Spawns colonies in-process via ``runtime.spawn_colony()`` and collects
transcripts via ``build_transcript()``. No HTTP or MCP dependency.

Results are saved to ``{data_dir}/eval/results/{task_id}/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from formicos.core.settings import load_castes, load_config
from formicos.core.types import CasteSlot
from formicos.surface.transcript import build_transcript

log = structlog.get_logger()

_STRATEGIES = ("stigmergic", "sequential")

_POLL_INTERVAL_S = 1.0
_POLL_TIMEOUT_S = 600.0  # 10 minutes max per colony

# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

_DEFAULT_TASKS_DIR = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"


def _load_task(task_id: str, tasks_dir: Path | None = None) -> dict[str, Any]:
    """Load a single task YAML by id."""
    base = tasks_dir or _DEFAULT_TASKS_DIR
    path = base / f"{task_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def _list_tasks(tasks_dir: Path | None = None) -> list[str]:
    """Return sorted list of available task ids."""
    base = tasks_dir or _DEFAULT_TASKS_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def _parse_castes(raw: list[dict[str, Any]]) -> list[CasteSlot]:
    """Convert task YAML caste dicts to CasteSlot instances."""
    return [CasteSlot.model_validate(c) for c in raw]


# ---------------------------------------------------------------------------
# Runtime bootstrap (minimal, no HTTP)
# ---------------------------------------------------------------------------


async def _bootstrap(
    config_path: Path,
    castes_path: Path,
) -> tuple[Any, Any, Any, Path]:
    """Create a minimal Runtime + ColonyManager for in-process evaluation.

    Returns (runtime, colony_manager, projections, data_dir).
    """
    from formicos.adapters.store_sqlite import SqliteEventStore
    from formicos.surface.colony_manager import ColonyManager
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import LLMRouter, Runtime
    from formicos.surface.ws_handler import WebSocketManager

    settings = load_config(config_path)
    castes = load_castes(castes_path) if castes_path.exists() else None

    data_dir = Path(settings.system.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Event store (lazy-init via _ensure_db on first use)
    event_store = SqliteEventStore(data_dir / "eval_events.db")

    # Projections
    projections = ProjectionStore()

    # LLM adapters (reuse app.py pattern)
    adapters = _build_adapters(settings)

    # Cost function
    rate_map: dict[str, tuple[float, float]] = {}
    for m in settings.models.registry:
        rate_map[m.address] = (
            m.cost_per_input_token or 0.0,
            m.cost_per_output_token or 0.0,
        )

    def cost_fn(model: str, input_tokens: int, output_tokens: int) -> float:
        rates = rate_map.get(model, (0.0, 0.0))
        return (input_tokens * rates[0]) + (output_tokens * rates[1])

    # LLM router
    router = LLMRouter(
        adapters=adapters,
        routing_table=settings.routing.model_routing,
        registry=settings.models.registry,
    )

    # Interpolate config once for embedding + vector store setup
    from formicos.core.settings import (
        _interpolate_recursive,  # pyright: ignore[reportPrivateUsage]
    )

    with config_path.open("r", encoding="utf-8") as fh:
        raw_yaml = yaml.safe_load(fh)
    raw_cfg: dict[str, Any] = _interpolate_recursive(raw_yaml) or {}  # pyright: ignore[reportAssignmentType]

    # Embedding (best-effort)
    embed_fn = None
    embed_client = None
    try:
        from formicos.adapters.embedding_qwen3 import Qwen3Embedder

        embed_cfg = dict(raw_cfg.get("embedding", {}))  # pyright: ignore[reportUnknownArgumentType]
        endpoint = str(embed_cfg.get("endpoint", ""))
        if endpoint:
            embed_client = Qwen3Embedder(
                url=endpoint,
                instruction=str(embed_cfg.get("instruction", "")),
            )
    except Exception:  # noqa: BLE001
        pass

    # Vector store (best-effort)
    vector_store = None
    try:
        from formicos.adapters.vector_qdrant import QdrantVectorPort

        # Use interpolated config (raw_cfg from embed block) so env vars
        # like ${QDRANT_URL:...} are resolved, not passed as literal strings.
        vec_cfg = dict(raw_cfg.get("vector", {}))  # pyright: ignore[reportUnknownArgumentType]
        if embed_client is not None or embed_fn is not None:
            vector_store = QdrantVectorPort(
                url=vec_cfg.get("qdrant_url", "http://localhost:6333"),
                embed_fn=embed_fn,
                embed_client=embed_client,
                prefer_grpc=bool(vec_cfg.get("qdrant_prefer_grpc", True)),
                default_collection=vec_cfg.get("collection_name", "skill_bank_v2"),
                vector_dimensions=settings.embedding.dimensions,
            )
    except Exception:  # noqa: BLE001
        pass

    # WS manager (no-op — no connected clients)
    ws_manager = WebSocketManager(
        projections=projections,
        settings=settings,
        castes=castes,
    )

    # Runtime
    runtime = Runtime(
        event_store=event_store,  # type: ignore[arg-type]
        projections=projections,
        ws_manager=ws_manager,
        settings=settings,
        castes=castes,
        llm_router=router,
        embed_fn=embed_fn,
        vector_store=vector_store,
        cost_fn=cost_fn,
        embed_client=embed_client,
    )

    # Colony manager
    colony_manager = ColonyManager(runtime)
    runtime.colony_manager = colony_manager

    # -- Knowledge catalog (mirrors production app.py wiring) --
    from formicos.surface.memory_store import MemoryStore

    memory_store: MemoryStore | None = None
    if vector_store is not None:
        memory_store = MemoryStore(vector_port=vector_store)  # type: ignore[arg-type]

    from formicos.surface.knowledge_catalog import KnowledgeCatalog

    skill_collection = "skill_bank_v2"
    if vector_store is not None:
        skill_collection = getattr(vector_store, "_default_collection", "skill_bank_v2")

    knowledge_catalog = KnowledgeCatalog(
        memory_store=memory_store,
        vector_port=vector_store,  # type: ignore[arg-type]
        skill_collection=skill_collection,
        projections=projections,
        kg_adapter=None,  # Wave 59.5: no KG in eval runtime
    )

    runtime.memory_store = memory_store
    runtime.knowledge_catalog = knowledge_catalog  # type: ignore[attr-defined]

    # Replay existing events into projections
    async for event in event_store.replay():
        projections.apply(event)

    # Rebuild memory store vectors from projection state (post-replay)
    if memory_store is not None and projections.memory_entries:
        mem_count = await memory_store.rebuild_from_projection(
            projections.memory_entries,
        )
        log.info("eval.memory_store_rebuilt", entries=mem_count)

    return runtime, colony_manager, projections, data_dir


def _build_adapters(
    settings: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Build LLM provider adapters from settings (mirrors app.py logic)."""
    adapters: dict[str, Any] = {}

    # Anthropic
    try:
        import os

        from formicos.adapters.llm_anthropic import AnthropicLLMAdapter

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            adapters["anthropic"] = AnthropicLLMAdapter(api_key=api_key)
    except Exception:  # noqa: BLE001
        pass

    # Gemini
    try:
        import os

        from formicos.adapters.llm_gemini import GeminiAdapter

        if os.environ.get("GEMINI_API_KEY"):
            adapters["gemini"] = GeminiAdapter()
    except Exception:  # noqa: BLE001
        pass

    # OpenAI-compatible (llama-cpp, ollama, ollama-cloud)
    try:
        import os as _os  # noqa: PLC0415

        from formicos.adapters.llm_openai_compatible import (
            OpenAICompatibleLLMAdapter,
        )

        for rec in settings.models.registry:
            prefix = rec.address.split("/", 1)[0]
            if prefix in ("anthropic", "gemini"):
                continue
            if prefix not in adapters:
                endpoint = rec.endpoint
                if endpoint:
                    stripped = endpoint.rstrip("/")
                    if not stripped.endswith("/v1"):
                        endpoint = f"{stripped}/v1"
                    # Wave 58: scale timeout by time_multiplier for slow
                    # providers (cloud archivist, CPU models).
                    max_mult = max(
                        (r.time_multiplier or 1.0
                         for r in settings.models.registry
                         if r.address.startswith(prefix + "/")),
                        default=1.0,
                    )
                    api_key = (
                        _os.environ.get(rec.api_key_env or "", "")
                        if rec.api_key_env else None
                    )
                    adapters[prefix] = OpenAICompatibleLLMAdapter(
                        base_url=endpoint,
                        api_key=api_key if api_key else None,
                        timeout_s=120.0 * max(1.0, max_mult),
                    )
    except Exception:  # noqa: BLE001
        pass

    return adapters


# ---------------------------------------------------------------------------
# Colony execution
# ---------------------------------------------------------------------------


async def _wait_for_colony(
    projections: Any,  # noqa: ANN401
    colony_id: str,
    timeout_s: float = _POLL_TIMEOUT_S,
) -> str:
    """Poll projection until colony is no longer running. Returns final status."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        colony = projections.get_colony(colony_id)
        if colony is not None and colony.status not in ("pending", "running"):
            return str(colony.status)
        await asyncio.sleep(_POLL_INTERVAL_S)
    return "timeout"


async def _run_single(
    runtime: Any,  # noqa: ANN401
    colony_manager: Any,  # noqa: ANN401
    projections: Any,  # noqa: ANN401
    task: dict[str, Any],
    strategy: str,
    workspace_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """Run a single colony and return its result record."""
    castes = _parse_castes(task["castes"])
    model_assignments: dict[str, str] = task.get("model_assignments") or {}

    wall_start = time.monotonic()
    colony_id = await runtime.spawn_colony(
        workspace_id=workspace_id,
        thread_id=thread_id,
        task=task["description"],
        castes=castes,
        strategy=strategy,
        max_rounds=task.get("max_rounds", 25),
        budget_limit=task.get("budget_limit", 5.0),
        model_assignments=model_assignments,
    )

    # Start the colony round loop
    await colony_manager.start_colony(colony_id)

    # Wait for completion
    status = await _wait_for_colony(projections, colony_id)
    wall_time_s = round(time.monotonic() - wall_start, 2)

    # Collect transcript
    colony_proj = projections.get_colony(colony_id)
    transcript: dict[str, Any] = {}
    if colony_proj is not None:
        transcript = build_transcript(colony_proj)

    return {
        "colony_id": colony_id,
        "task_id": task["id"],
        "strategy": strategy,
        "status": status,
        "quality_score": transcript.get("quality_score", 0.0),
        "cost": transcript.get("cost", 0.0),
        "wall_time_s": wall_time_s,
        "rounds_completed": transcript.get("rounds_completed", 0),
        "redirect_history": transcript.get("redirect_history", []),
        "input_sources": transcript.get("input_sources", []),
        "skills_extracted": (
            getattr(colony_proj, "entries_extracted_count", 0)
            if colony_proj is not None
            else 0
        ),
        "team": transcript.get("team", []),
        "transcript": transcript,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------


def _save_result(
    result: dict[str, Any],
    results_dir: Path,
) -> Path:
    """Save a single run result as JSON. Returns the file path."""
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{result['strategy']}_run{result.get('run_index', 0):02d}"
        f"_{result['colony_id']}.json"
    )
    path = results_dir / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run_eval(
    task_id: str,
    runs: int = 3,
    config_path: Path | None = None,
    castes_path: Path | None = None,
    tasks_dir: Path | None = None,
) -> None:
    """Run the full A/B evaluation for a task."""
    project_root = Path(__file__).resolve().parents[3]
    cfg = config_path or project_root / "config" / "formicos.yaml"
    cst = castes_path or project_root / "config" / "caste_recipes.yaml"

    runtime, colony_manager, projections, data_dir = await _bootstrap(cfg, cst)

    # Load task(s)
    task_ids = _list_tasks(tasks_dir) if task_id == "all" else [task_id]

    if not task_ids:
        log.error("eval.no_tasks_found")
        return

    results_base = data_dir / "eval" / "results"

    for tid in task_ids:
        task = _load_task(tid, tasks_dir)
        task_results_dir = results_base / tid
        log.info("eval.task_start", task_id=tid, runs=runs)

        # Ensure workspace and thread exist
        ws_id = "eval-workspace"
        thread_id = f"eval-{tid}"
        if projections.workspaces.get(ws_id) is None:
            await runtime.create_workspace(ws_id)
        if projections.get_thread(ws_id, thread_id) is None:
            await runtime.create_thread(ws_id, thread_id)

        for run_idx in range(runs):
            for strategy in _STRATEGIES:
                log.info(
                    "eval.run_start",
                    task_id=tid,
                    strategy=strategy,
                    run=run_idx + 1,
                    of=runs,
                )
                result = await _run_single(
                    runtime=runtime,
                    colony_manager=colony_manager,
                    projections=projections,
                    task=task,
                    strategy=strategy,
                    workspace_id=ws_id,
                    thread_id=thread_id,
                )
                result["run_index"] = run_idx
                path = _save_result(result, task_results_dir)
                log.info(
                    "eval.run_complete",
                    task_id=tid,
                    strategy=strategy,
                    status=result["status"],
                    quality=result["quality_score"],
                    cost=result["cost"],
                    wall_time_s=result["wall_time_s"],
                    rounds=result["rounds_completed"],
                    saved=str(path),
                )

        log.info("eval.task_complete", task_id=tid)

    log.info(
        "eval.done",
        results_dir=str(results_base),
        tasks=task_ids,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formicos.eval.run",
        description="FormicOS A/B evaluation harness: stigmergic vs sequential.",
    )
    parser.add_argument(
        "--task",
        default=None,
        help='Task id to evaluate (or "all" for every task in the suite).',
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of paired runs per strategy (default: 3).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to formicos.yaml (default: config/formicos.yaml).",
    )
    parser.add_argument(
        "--castes-config",
        default=None,
        help="Path to caste_recipes.yaml (default: config/caste_recipes.yaml).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available task ids and exit.",
    )

    args = parser.parse_args()

    if args.list:
        for tid in _list_tasks():
            task = _load_task(tid)
            desc = task.get("description", "")[:70]
            print(f"  {tid:<25} [{task.get('difficulty', '?')}]  {desc}")  # noqa: T201
        sys.exit(0)

    if args.task is None:
        parser.error("--task is required (or use --list to see available tasks)")

    config_path = Path(args.config) if args.config else None
    castes_path = Path(args.castes_config) if args.castes_config else None

    asyncio.run(run_eval(
        task_id=args.task,
        runs=args.runs,
        config_path=config_path,
        castes_path=castes_path,
    ))


if __name__ == "__main__":
    main()
