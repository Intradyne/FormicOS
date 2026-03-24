"""Additional local-model fixtures for Queen intent parsing."""

from __future__ import annotations

from formicos.adapters.queen_intent_parser import (
    intent_to_tool_call,
    parse_intent_regex,
)


def test_parse_spawn_tool_name_prose_with_task_field() -> None:
    text = (
        'I will use spawn_colony to create a colony with task="build the API layer" '
        'and castes=["coder"].'
    )

    result = parse_intent_regex(text)

    assert result == {"action": "SPAWN", "objective": "build the API layer"}


def test_parse_preview_summary_as_preview_spawn() -> None:
    text = (
        "Task: build the API layer\n"
        "Team: coder (standard, 1 agent)\n"
        "Rounds: 4\n"
        "Budget: $0.50\n"
        "Why: The task is simple and deterministic.\n"
        "Preview complete. Ready to spawn. Confirm to proceed."
    )

    result = parse_intent_regex(text)

    assert result is not None
    assert result["action"] == "PREVIEW_SPAWN"
    assert result["objective"] == "build the API layer"
    assert result["castes"] == [{"caste": "coder", "tier": "standard", "count": 1}]
    assert result["max_rounds"] == 4
    assert result["budget_limit"] == 0.5

    tool_call = intent_to_tool_call(result)

    assert tool_call["name"] == "spawn_colony"
    assert tool_call["input"]["preview"] is True
