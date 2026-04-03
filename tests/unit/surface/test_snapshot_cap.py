"""Wave 87 Track C: bounded snapshot cap tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from formicos.surface.view_state import _build_tree, _MAX_COLONIES_PER_THREAD


@dataclass
class _FakeColony:
    id: str = "c-1"
    display_name: str = ""
    status: str = "completed"
    round_number: int = 1
    max_rounds: int = 5
    task: str = "test"
    strategy: str = "sequential"
    convergence: float = 0.0
    cost: float = 0.0
    budget_limit: float = 1.0
    castes: list[Any] = field(default_factory=list)
    agents: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.7
    skills_extracted: int = 0
    chat_messages: list[Any] = field(default_factory=list)
    round_records: list[Any] = field(default_factory=list)
    active_goal: str = ""
    pheromone_weights: dict[Any, float] | None = None
    redirect_history: list[Any] = field(default_factory=list)
    routing_override: dict[str, Any] | None = None
    validator_verdict: str | None = None
    validator_task_type: str | None = None
    validator_reason: str | None = None
    productive_calls: int = 0
    observation_calls: int = 0
    knowledge_accesses: list[Any] = field(default_factory=list)
    service_type: str | None = None
    template_id: str = ""


@dataclass
class _FakeThread:
    id: str = "t-1"
    name: str = "test"
    status: str = "active"
    colonies: dict[str, _FakeColony] = field(default_factory=dict)


@dataclass
class _FakeWorkspace:
    id: str = "ws-1"
    name: str = "test"
    config: dict[str, Any] = field(default_factory=dict)
    threads: dict[str, _FakeThread] = field(default_factory=dict)


@dataclass
class _FakeStore:
    workspaces: dict[str, _FakeWorkspace] = field(default_factory=dict)
    colonies: dict[str, Any] = field(default_factory=dict)
    budgets: dict[str, Any] = field(default_factory=dict)


class TestArchivedThreadsExcluded:
    def test_archived_thread_not_in_tree(self) -> None:
        ws = _FakeWorkspace(threads={
            "t-active": _FakeThread(id="t-active", status="active"),
            "t-archived": _FakeThread(id="t-archived", status="archived"),
        })
        store = _FakeStore(workspaces={"ws-1": ws})
        tree = _build_tree(store)  # type: ignore[arg-type]
        thread_ids = [c["id"] for c in tree[0]["children"]]
        assert "t-active" in thread_ids
        assert "t-archived" not in thread_ids

    def test_completed_thread_still_included(self) -> None:
        ws = _FakeWorkspace(threads={
            "t-done": _FakeThread(id="t-done", status="completed"),
        })
        store = _FakeStore(workspaces={"ws-1": ws})
        tree = _build_tree(store)  # type: ignore[arg-type]
        assert len(tree[0]["children"]) == 1


class TestColonyCap:
    def test_caps_colonies_per_thread(self) -> None:
        colonies = {
            f"c-{i}": _FakeColony(id=f"c-{i}")
            for i in range(30)
        }
        thread = _FakeThread(id="t-1", colonies=colonies)
        ws = _FakeWorkspace(threads={"t-1": thread})
        store = _FakeStore(workspaces={"ws-1": ws})
        tree = _build_tree(store)  # type: ignore[arg-type]
        colony_nodes = tree[0]["children"][0]["children"]
        assert len(colony_nodes) == _MAX_COLONIES_PER_THREAD

    def test_small_thread_not_capped(self) -> None:
        colonies = {f"c-{i}": _FakeColony(id=f"c-{i}") for i in range(5)}
        thread = _FakeThread(id="t-1", colonies=colonies)
        ws = _FakeWorkspace(threads={"t-1": thread})
        store = _FakeStore(workspaces={"ws-1": ws})
        tree = _build_tree(store)  # type: ignore[arg-type]
        colony_nodes = tree[0]["children"][0]["children"]
        assert len(colony_nodes) == 5
