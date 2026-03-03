"""
Tests for FormicOS v0.7.3 MetricsAccumulator (orchestrator.py).

Covers:
- record_round sums tokens correctly
- record_round counts tool calls
- record_round tracks agent_activity and caste_activity
- get_colony_metrics aggregates across rounds
- total_tokens property sums prompt + completion
- Empty agent_outputs produce zero metrics
- Multiple rounds accumulate correctly
"""

from __future__ import annotations


from src.orchestrator import MetricsAccumulator


class FakeAgentOutput:
    """Minimal AgentOutput substitute for metrics tests."""

    def __init__(
        self,
        tokens_prompt: int = 0,
        tokens_completion: int = 0,
        tokens_used: int = 0,
        tool_calls: list | None = None,
    ) -> None:
        self.tokens_prompt = tokens_prompt
        self.tokens_completion = tokens_completion
        self.tokens_used = tokens_used
        self.tool_calls = tool_calls or []


# ── Basic accumulation ─────────────────────────────────────────────────


def test_record_round_sums_tokens():
    acc = MetricsAccumulator("colony-1")

    outputs = {
        "agent_a": FakeAgentOutput(tokens_prompt=100, tokens_completion=50),
        "agent_b": FakeAgentOutput(tokens_prompt=200, tokens_completion=80),
    }
    rm = acc.record_round(round_num=1, agent_outputs=outputs, duration_ms=1000.0)

    assert rm.tokens_prompt == 300
    assert rm.tokens_completion == 130
    assert rm.round_num == 1
    assert rm.duration_ms == 1000.0


def test_record_round_counts_tool_calls():
    acc = MetricsAccumulator("colony-1")

    outputs = {
        "agent_a": FakeAgentOutput(
            tokens_prompt=100, tokens_completion=50,
            tool_calls=["call1", "call2", "call3", "call4", "call5"],
        ),
        "agent_b": FakeAgentOutput(
            tokens_prompt=50, tokens_completion=30,
            tool_calls=["call6"],
        ),
    }
    rm = acc.record_round(round_num=1, agent_outputs=outputs, duration_ms=500.0)

    assert rm.tool_calls_count == 6  # 5 + 1


def test_record_round_agent_activity():
    acc = MetricsAccumulator("colony-1")

    outputs = {
        "agent_a": FakeAgentOutput(tokens_prompt=100, tokens_completion=50),
        "agent_b": FakeAgentOutput(tokens_prompt=200, tokens_completion=80),
    }
    rm = acc.record_round(round_num=1, agent_outputs=outputs, duration_ms=500.0)

    assert rm.agent_activity["agent_a"] == 150
    assert rm.agent_activity["agent_b"] == 280


def test_record_round_caste_activity():
    acc = MetricsAccumulator("colony-1")

    outputs = {
        "agent_a": FakeAgentOutput(tokens_prompt=100, tokens_completion=50),
        "agent_b": FakeAgentOutput(tokens_prompt=200, tokens_completion=80),
    }
    castes = {"agent_a": "architect", "agent_b": "coder"}
    rm = acc.record_round(
        round_num=1, agent_outputs=outputs, duration_ms=500.0,
        agent_castes=castes,
    )

    assert rm.caste_activity["architect"] == 150
    assert rm.caste_activity["coder"] == 280


# ── Colony-level aggregation ──────────────────────────────────────────


def test_get_colony_metrics_aggregates():
    acc = MetricsAccumulator("colony-1")

    acc.record_round(
        round_num=1,
        agent_outputs={
            "a": FakeAgentOutput(tokens_prompt=100, tokens_completion=50),
        },
        duration_ms=500.0,
    )
    acc.record_round(
        round_num=2,
        agent_outputs={
            "a": FakeAgentOutput(tokens_prompt=200, tokens_completion=100),
        },
        duration_ms=700.0,
    )

    cm = acc.get_colony_metrics()
    assert cm.colony_id == "colony-1"
    assert cm.total_tokens_prompt == 300
    assert cm.total_tokens_completion == 150
    assert len(cm.rounds) == 2


def test_total_tokens_property():
    acc = MetricsAccumulator("colony-1")

    acc.record_round(
        round_num=1,
        agent_outputs={
            "a": FakeAgentOutput(tokens_prompt=100, tokens_completion=50),
        },
        duration_ms=500.0,
    )

    assert acc.total_tokens == 150


def test_empty_outputs():
    acc = MetricsAccumulator("colony-1")

    rm = acc.record_round(round_num=1, agent_outputs={}, duration_ms=100.0)

    assert rm.tokens_prompt == 0
    assert rm.tokens_completion == 0
    assert rm.tool_calls_count == 0
    assert rm.agent_activity == {}


def test_multiple_rounds_accumulate():
    acc = MetricsAccumulator("colony-1")

    for i in range(5):
        acc.record_round(
            round_num=i + 1,
            agent_outputs={
                "a": FakeAgentOutput(tokens_prompt=10, tokens_completion=5),
            },
            duration_ms=100.0,
        )

    cm = acc.get_colony_metrics()
    assert cm.total_tokens_prompt == 50
    assert cm.total_tokens_completion == 25
    assert cm.total_tool_calls == 0
    assert len(cm.rounds) == 5
    assert acc.total_tokens == 75
