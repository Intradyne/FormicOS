"""Wave 40 1A: Lightweight profiling harness for backend hot paths.

Measures wall-clock time for the five required paths:
  1. generate_briefing with large memory state
  2. retrieval scoring / composite-key sorting
  3. view-state snapshot generation
  4. colony spawn-to-first-round latency (event construction)
  5. projection replay / rebuild time

Run:
    python tests/benchmark/profiling_harness.py
"""

from __future__ import annotations

import random
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOMAINS = ["auth", "payments", "api", "frontend", "infra", "ml", "data"]
_STATUSES = ["candidate", "verified", "stable", "stale"]
_POLARITIES = ["positive", "negative", "neutral"]
_STRATEGIES = ["stigmergic", "sequential"]
_CASTES = ["coder", "reviewer", "researcher"]


def _ts(days_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _make_entry(eid: int, workspace_id: str = "ws-1") -> tuple[str, dict[str, Any]]:
    entry_id = f"entry-{eid:04d}"
    return entry_id, {
        "id": entry_id,
        "workspace_id": workspace_id,
        "title": f"Knowledge entry {eid} about {random.choice(_DOMAINS)}",
        "content": f"Detailed content for entry {eid}. " * 10,
        "status": random.choice(_STATUSES),
        "polarity": random.choice(_POLARITIES),
        "domains": random.sample(_DOMAINS, k=random.randint(1, 3)),
        "conf_alpha": round(random.uniform(1, 30), 2),
        "conf_beta": round(random.uniform(1, 15), 2),
        "prediction_error_count": random.randint(0, 5),
        "created_at": _ts(random.randint(0, 180)),
        "updated_at": _ts(random.randint(0, 30)),
        "decay_class": random.choice(["ephemeral", "stable", "permanent"]),
        "entry_type": random.choice(["skill", "experience"]),
        "sub_type": "technique",
        "peak_alpha": round(random.uniform(5, 35), 2),
        "score": round(random.uniform(0.3, 0.95), 3),
        "thread_id": f"th-{random.randint(1, 5)}",
    }


def _make_outcome(cid: int, workspace_id: str = "ws-1") -> Any:
    """Create a mock ColonyOutcome-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        colony_id=f"col-{cid:04d}",
        workspace_id=workspace_id,
        thread_id=f"th-{random.randint(1, 5)}",
        succeeded=random.choice([True, True, True, False]),
        total_rounds=random.randint(1, 15),
        total_cost=round(random.uniform(0.01, 2.0), 3),
        duration_ms=random.randint(5000, 120000),
        entries_extracted=random.randint(0, 5),
        entries_accessed=random.randint(0, 10),
        quality_score=round(random.uniform(0.3, 0.95), 3),
        caste_composition=random.sample(_CASTES, k=random.randint(1, 2)),
        strategy=random.choice(_STRATEGIES),
        maintenance_source=None,
        escalated=False,
        starting_tier="standard",
        escalated_tier=None,
        escalation_reason=None,
        escalation_round=None,
        pre_escalation_cost=None,
        validator_verdict=random.choice(["pass", "fail", "inconclusive", None]),
        validator_task_type=random.choice(["code", "research", None]),
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def _bench(label: str, fn: Any, iterations: int = 5) -> dict[str, float]:
    """Run fn() `iterations` times, return timing stats in ms."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)
    return {
        "label": label,
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "mean_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "stdev_ms": round(statistics.stdev(times), 2) if len(times) > 1 else 0,
    }


def run_profiling() -> list[dict[str, Any]]:
    """Run all profiling benchmarks and return results."""
    results: list[dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # 1. generate_briefing with large memory state
    # -----------------------------------------------------------------------
    from types import SimpleNamespace

    from formicos.surface.proactive_intelligence import generate_briefing

    entry_counts = [100, 500]
    for n_entries in entry_counts:
        entries = dict(_make_entry(i) for i in range(n_entries))
        outcomes = {f"col-{i:04d}": _make_outcome(i) for i in range(n_entries // 5)}

        projections = SimpleNamespace(
            memory_entries=entries,
            colony_outcomes=outcomes,
            cooccurrence_weights={},
            peer_trust_scores={},
            federation_inbound_signals=[],
            colonies={},
        )

        def _run_briefing(p=projections, ws="ws-1") -> None:
            generate_briefing(ws, p)

        r = _bench(f"generate_briefing ({n_entries} entries)", _run_briefing)
        results.append(r)

    # -----------------------------------------------------------------------
    # 2. Retrieval scoring / composite-key sorting
    # -----------------------------------------------------------------------
    from formicos.surface.knowledge_catalog import _composite_key

    search_results = [
        {
            "id": f"entry-{i:04d}",
            "score": round(random.uniform(0.3, 0.95), 3),
            "conf_alpha": round(random.uniform(1, 30), 2),
            "conf_beta": round(random.uniform(1, 15), 2),
            "created_at": _ts(random.randint(0, 180)),
            "status": random.choice(_STATUSES),
            "thread_bonus": random.choice([0.0, 1.0]),
            "is_pinned": False,
            "peer_id": None,
        }
        for i in range(200)
    ]

    def _run_scoring() -> None:
        for item in search_results:
            _composite_key(item)

    r = _bench("composite_key scoring (200 items)", _run_scoring, iterations=10)
    results.append(r)

    # Sort benchmark
    def _run_sort() -> None:
        items = list(search_results)
        items.sort(key=_composite_key)

    r = _bench("composite_key sort (200 items)", _run_sort, iterations=10)
    results.append(r)

    # -----------------------------------------------------------------------
    # 3. View-state snapshot generation
    # -----------------------------------------------------------------------
    from formicos.surface.projections import (
        ColonyProjection,
        ProjectionStore,
        RoundProjection,
    )
    from formicos.surface.view_state import build_snapshot

    store = ProjectionStore()

    # Populate store with realistic data
    from types import SimpleNamespace as NS

    ws = NS(
        id="ws-1", name="Test Workspace",
        threads={}, children=[], config={},
        model_registry={}, model_assignments={},
    )
    store.workspaces["ws-1"] = ws

    for i in range(20):
        col_id = f"col-{i:04d}"
        colony = ColonyProjection(
            id=col_id, thread_id="th-1", workspace_id="ws-1",
            task=f"Test task {i}", status="completed",
            round_number=5, max_rounds=10,
            quality_score=0.75, cost=1.5,
        )
        # Add some rounds
        for r_num in range(1, 6):
            rp = RoundProjection(round_number=r_num)
            rp.convergence = round(random.uniform(0.3, 0.95), 3)
            rp.cost = round(random.uniform(0.01, 0.5), 3)
            colony.round_records.append(rp)
        store.colonies[col_id] = colony

    from formicos.core.settings import (
        EmbeddingConfig,
        GovernanceConfig,
        ModelDefaults,
        ModelsConfig,
        RoutingConfig,
        SystemConfig,
        SystemSettings,
    )

    settings = SystemSettings(
        system=SystemConfig(host="0.0.0.0", port=8080, data_dir="./data"),
        models=ModelsConfig(
            defaults=ModelDefaults(
                queen="test/model", coder="test/model",
                reviewer="test/model", researcher="test/model",
                archivist="test/model",
            ),
            registry=[],
        ),
        embedding=EmbeddingConfig(model="test-model", dimensions=384),
        governance=GovernanceConfig(
            max_rounds_per_colony=25, stall_detection_window=3,
            convergence_threshold=0.95, default_budget_per_colony=1.0,
        ),
        routing=RoutingConfig(
            default_strategy="stigmergic", tau_threshold=0.35,
            k_in_cap=5, pheromone_decay_rate=0.1, pheromone_reinforce_rate=0.3,
        ),
    )

    def _run_snapshot() -> None:
        build_snapshot(store, settings)

    # Warmup
    _run_snapshot()
    r = _bench("build_snapshot (20 colonies, 5 rounds each)", _run_snapshot)
    results.append(r)

    # -----------------------------------------------------------------------
    # 4. Colony spawn-to-first-round latency (event construction)
    # -----------------------------------------------------------------------
    from formicos.core.events import RoundCompleted, RoundStarted
    from formicos.core.types import CasteSlot

    def _run_event_construction() -> None:
        now = datetime.now(UTC)
        RoundStarted(
            seq=0, timestamp=now, address="ws-1/th-1/col-1",
            colony_id="col-1", round_number=1,
        )
        RoundCompleted(
            seq=0, timestamp=now, address="ws-1/th-1/col-1",
            colony_id="col-1", round_number=1,
            convergence=0.5, cost=0.1, duration_ms=5000,
        )

    r = _bench("event construction (RoundStarted+RoundCompleted)", _run_event_construction, iterations=20)
    results.append(r)

    # -----------------------------------------------------------------------
    # 5. Projection replay / rebuild time
    # -----------------------------------------------------------------------
    def _build_event_stream(n_rounds: int = 50) -> list:
        """Build a realistic event stream for replay (round lifecycle events)."""
        events = []
        now = datetime.now(UTC)
        addr = "ws-1/th-1/col-replay"

        seq = 1
        for r_num in range(1, n_rounds + 1):
            events.append(RoundStarted(
                seq=seq, timestamp=now, address=addr,
                colony_id="col-replay", round_number=r_num,
            ))
            seq += 1

            events.append(RoundCompleted(
                seq=seq, timestamp=now, address=addr,
                colony_id="col-replay", round_number=r_num,
                convergence=min(0.5 + r_num * 0.01, 0.95),
                cost=0.05, duration_ms=3000,
            ))
            seq += 1

        return events

    for n_rounds in [10, 50]:
        event_stream = _build_event_stream(n_rounds)

        def _run_replay(events=event_stream) -> None:
            s = ProjectionStore()
            s.replay(events)

        r = _bench(
            f"projection replay ({n_rounds} rounds, {len(event_stream)} events)",
            _run_replay,
        )
        results.append(r)

    return results


def _format_results(results: list[dict[str, Any]]) -> str:
    """Format profiling results as a markdown table."""
    lines = [
        "| Path | Min (ms) | Mean (ms) | Median (ms) | Max (ms) | Stdev |",
        "|------|----------|-----------|-------------|----------|-------|",
    ]
    for r in results:
        lines.append(
            f"| {r['label']} | {r['min_ms']} | {r['mean_ms']} "
            f"| {r['median_ms']} | {r['max_ms']} | {r['stdev_ms']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print("Wave 40 1A: Backend Profiling Harness")
    print("=" * 60)
    results = run_profiling()
    print()
    print(_format_results(results))
    print()
    for r in results:
        print(f"  {r['label']}: {r['mean_ms']:.1f}ms mean ({r['min_ms']:.1f}-{r['max_ms']:.1f}ms)")
