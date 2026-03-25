"""Unit tests for the Queen intent fallback parser (Wave 13).

Fixtures model real failure outputs from Qwen3-30B-A3B where the model
produces prose instead of structured tool calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.adapters.queen_intent_parser import (
    intent_to_tool_call,
    parse_intent_regex,
    parse_queen_intent,
)

# ---------------------------------------------------------------------------
# Real failure fixtures — prose that Qwen3-30B-A3B produces when tool-calling
# fails.  Each fixture has the raw text and the expected parsed intent.
# ---------------------------------------------------------------------------

SPAWN_FIXTURES: list[tuple[str, dict[str, Any]]] = [
    # Fixture 1: "Let's spawn" pattern
    (
        "Let's spawn a colony for implementing the authentication module with JWT tokens.",
        {"action": "SPAWN", "objective": "implementing the authentication module with JWT tokens"},
    ),
    # Fixture 2: "I'll create" pattern
    (
        "I'll create a new colony to refactor the database layer to use async queries.",
        {"action": "SPAWN", "objective": "refactor the database layer to use async queries"},
    ),
    # Fixture 3: "I will launch" pattern
    (
        "I will launch a colony for fixing the race condition in the event loop.",
        {"action": "SPAWN", "objective": "fixing the race condition in the event loop"},
    ),
    # Fixture 4: "We should start" pattern
    (
        "We should start a colony to add comprehensive error handling to the API endpoints.",
        {"action": "SPAWN", "objective": "add comprehensive error handling to the API endpoints"},
    ),
    # Fixture 5: Gerund "Spawning" form
    (
        "Spawning a new colony for writing integration tests for the skill bank.",
        {"action": "SPAWN", "objective": "writing integration tests for the skill bank"},
    ),
    # Fixture 6: "I recommend" pattern
    (
        "I recommend creating a colony to optimize the vector search query pipeline.",
        {"action": "SPAWN", "objective": "optimize the vector search query pipeline"},
    ),
    # Fixture 7: "Going to" pattern
    (
        "Going to spawn a colony for migrating the configuration to YAML format.",
        {"action": "SPAWN", "objective": "migrating the configuration to YAML format"},
    ),
    # Fixture 8: "I need to" pattern
    (
        "I need to create a colony to investigate the memory leak in the WebSocket handler.",
        {"action": "SPAWN", "objective": "investigate the memory leak in the WebSocket handler"},
    ),
    # Fixture 9: "Let us deploy" (formal)
    (
        "Let us deploy a colony for building the frontend dashboard components.",
        {"action": "SPAWN", "objective": "building the frontend dashboard components"},
    ),
    # Fixture 10: "Setting up" gerund
    (
        "Setting up a colony to handle the data pipeline ETL processing.",
        {"action": "SPAWN", "objective": "handle the data pipeline ETL processing"},
    ),
    # Fixture 11: "I want to" pattern
    (
        "I want to launch a colony for adding pagination to the skill browser API.",
        {"action": "SPAWN", "objective": "adding pagination to the skill browser API"},
    ),
    # Fixture 12: with "that will" clause
    (
        "Let's create a colony that will implement the caching layer for embeddings.",
        {"action": "SPAWN", "objective": "implement the caching layer for embeddings"},
    ),
]

KILL_FIXTURES: list[tuple[str, dict[str, Any]]] = [
    # Fixture 13: Direct "kill colony"
    (
        "Kill colony abc-123-def.",
        {"action": "KILL", "colony_id": "abc-123-def"},
    ),
    # Fixture 14: "Let's terminate"
    (
        "Let's terminate colony worker-42 since it's stalled.",
        {"action": "KILL", "colony_id": "worker-42"},
    ),
    # Fixture 15: "I'll stop"
    (
        "I'll stop the colony stuck-colony-7 because it's consuming too many resources.",
        {"action": "KILL", "colony_id": "stuck-colony-7"},
    ),
    # Fixture 16: "We should abort"
    (
        "We should abort colony test-run-99.",
        {"action": "KILL", "colony_id": "test-run-99"},
    ),
    # Fixture 17: "Going to shut down"
    (
        "Going to shut down colony old_migration.",
        {"action": "KILL", "colony_id": "old_migration"},
    ),
]

REDIRECT_FIXTURES: list[tuple[str, dict[str, Any]]] = [
    # Fixture 18: "Redirect colony X to Y"
    (
        "Redirect colony auth-impl to focus on OAuth2 integration instead.",
        {
            "action": "REDIRECT",
            "colony_id": "auth-impl",
            "new_objective": "focus on OAuth2 integration instead",
        },
    ),
    # Fixture 19: "Refocus colony X toward Y"
    (
        "Refocus colony data-layer toward optimizing query performance.",
        {
            "action": "REDIRECT",
            "colony_id": "data-layer",
            "new_objective": "optimizing query performance",
        },
    ),
]

APOPTOSIS_FIXTURES: list[tuple[str, dict[str, Any]]] = [
    # Fixture 20: "colony X should complete"
    (
        "Colony cleanup-task should complete and self-terminate now.",
        {"action": "APOPTOSIS", "colony_id": "cleanup-task"},
    ),
    # Fixture 21: "colony X can finish"
    (
        "Colony migration-v2 can finish since all data has been transferred.",
        {"action": "APOPTOSIS", "colony_id": "migration-v2"},
    ),
    # Fixture 22: "colony X is ready to wrap up"
    (
        "Colony test-suite is ready to wrap up after passing all assertions.",
        {"action": "APOPTOSIS", "colony_id": "test-suite"},
    ),
]

NO_INTENT_FIXTURES: list[str] = [
    # Pure informational prose
    "The colony is making good progress on the authentication module.",
    "I've analyzed the codebase and found several areas for improvement.",
    "Here's a summary of the current workspace status.",
    "",
    "   ",
    # Short ambiguous text
    "OK",
    "Sure, let me think about that.",
]


# ---------------------------------------------------------------------------
# parse_intent_regex tests
# ---------------------------------------------------------------------------


class TestParseIntentRegex:
    @pytest.mark.parametrize(
        ("text", "expected"),
        SPAWN_FIXTURES,
        ids=[f"spawn_{i}" for i in range(len(SPAWN_FIXTURES))],
    )
    def test_spawn_patterns(self, text: str, expected: dict[str, Any]) -> None:
        result = parse_intent_regex(text)
        assert result is not None, f"Failed to parse: {text!r}"
        assert result["action"] == "SPAWN"
        # Objective should be a reasonable substring
        assert expected["objective"].lower()[:20] in result["objective"].lower()

    @pytest.mark.parametrize(
        ("text", "expected"),
        KILL_FIXTURES,
        ids=[f"kill_{i}" for i in range(len(KILL_FIXTURES))],
    )
    def test_kill_patterns(self, text: str, expected: dict[str, Any]) -> None:
        result = parse_intent_regex(text)
        assert result is not None, f"Failed to parse: {text!r}"
        assert result["action"] == "KILL"
        assert result["colony_id"] == expected["colony_id"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        REDIRECT_FIXTURES,
        ids=[f"redirect_{i}" for i in range(len(REDIRECT_FIXTURES))],
    )
    def test_redirect_patterns(self, text: str, expected: dict[str, Any]) -> None:
        result = parse_intent_regex(text)
        assert result is not None, f"Failed to parse: {text!r}"
        assert result["action"] == "REDIRECT"
        assert result["colony_id"] == expected["colony_id"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        APOPTOSIS_FIXTURES,
        ids=[f"apoptosis_{i}" for i in range(len(APOPTOSIS_FIXTURES))],
    )
    def test_apoptosis_patterns(self, text: str, expected: dict[str, Any]) -> None:
        result = parse_intent_regex(text)
        assert result is not None, f"Failed to parse: {text!r}"
        assert result["action"] == "APOPTOSIS"
        assert result["colony_id"] == expected["colony_id"]

    @pytest.mark.parametrize(
        "text",
        NO_INTENT_FIXTURES,
        ids=[f"no_intent_{i}" for i in range(len(NO_INTENT_FIXTURES))],
    )
    def test_no_intent_detected(self, text: str) -> None:
        result = parse_intent_regex(text)
        assert result is None

    def test_spawn_regex_rate(self) -> None:
        """At least 80% of SPAWN fixtures must be caught by regex."""
        caught = sum(1 for text, _ in SPAWN_FIXTURES if parse_intent_regex(text) is not None)
        rate = caught / len(SPAWN_FIXTURES)
        assert rate >= 0.80, f"Spawn regex catch rate: {rate:.0%} (need ≥80%)"


# ---------------------------------------------------------------------------
# intent_to_tool_call tests
# ---------------------------------------------------------------------------


class TestIntentToToolCall:
    def test_spawn_to_tool_call(self) -> None:
        tc = intent_to_tool_call({"action": "SPAWN", "objective": "build auth"})
        assert tc["name"] == "spawn_colony"
        assert tc["input"]["task"] == "build auth"
        assert "castes" in tc["input"]

    def test_kill_to_tool_call(self) -> None:
        tc = intent_to_tool_call({"action": "KILL", "colony_id": "abc-123"})
        assert tc["name"] == "kill_colony"
        assert tc["input"]["colony_id"] == "abc-123"

    def test_apoptosis_maps_to_kill(self) -> None:
        tc = intent_to_tool_call({"action": "APOPTOSIS", "colony_id": "done-1"})
        assert tc["name"] == "kill_colony"
        assert tc["input"]["colony_id"] == "done-1"

    def test_redirect_returns_empty(self) -> None:
        tc = intent_to_tool_call({
            "action": "REDIRECT",
            "colony_id": "x",
            "new_objective": "y",
        })
        # No redirect tool exists yet
        assert tc == {} or tc.get("name") is None


# ---------------------------------------------------------------------------
# parse_queen_intent (two-pass) tests
# ---------------------------------------------------------------------------


class TestParseQueenIntent:
    @pytest.mark.anyio()
    async def test_regex_pass_returns_without_gemini(self) -> None:
        """Regex match should return immediately, no LLM call."""
        text = "Let's spawn a colony for building the API."
        intent, via = await parse_queen_intent(text, runtime=None)

        assert intent is not None
        assert intent["action"] == "SPAWN"
        assert via == "regex"

    @pytest.mark.anyio()
    async def test_no_intent_returns_none(self) -> None:
        text = "Everything looks good so far."
        intent, via = await parse_queen_intent(text, runtime=None)

        assert intent is None
        assert via == ""

    @pytest.mark.anyio()
    async def test_gemini_fallback_on_ambiguous_text(self) -> None:
        """When regex fails, Gemini Flash classification is attempted."""
        from formicos.core.types import LLMResponse

        # Use non-deliberative ambiguous text (no "I think" / "we could" patterns)
        text = "The database needs some work done on it soon."
        mock_runtime = MagicMock()
        mock_runtime.llm_router.complete = AsyncMock(
            return_value=LLMResponse(
                content='{"action": "SPAWN", "details": "database optimization"}',
                tool_calls=[],
                input_tokens=50,
                output_tokens=20,
                model="gemini/gemini-2.5-flash",
                stop_reason="end_turn",
            ),
        )

        intent, via = await parse_queen_intent(text, runtime=mock_runtime)

        assert intent is not None
        assert intent["action"] == "SPAWN"
        assert via == "gemini_flash"

    @pytest.mark.anyio()
    async def test_gemini_timeout_returns_none(self) -> None:
        """Gemini timeout should gracefully return None."""
        # Use non-deliberative ambiguous text
        text = "The database needs some work done on it soon."
        mock_runtime = MagicMock()
        mock_runtime.llm_router.complete = AsyncMock(
            side_effect=TimeoutError("timed out"),
        )

        intent, via = await parse_queen_intent(text, runtime=mock_runtime)

        assert intent is None
        assert via == ""

    @pytest.mark.anyio()
    async def test_deliberation_guard_blocks_spawn(self) -> None:
        """Wave 60.5: deliberative text should return DELIBERATE, not trigger Gemini."""
        text = "I think we might want to work on the database stuff."

        intent, via = await parse_queen_intent(text)

        assert intent is not None
        assert intent["action"] == "DELIBERATE"
        assert via == "regex"

    @pytest.mark.anyio()
    async def test_deliberation_showcase_question(self) -> None:
        """Wave 61: open-ended showcase question returns DELIBERATE."""
        text = "What about building a project showcase? Here are some ideas."

        intent, via = await parse_queen_intent(text)

        assert intent is not None
        assert intent["action"] == "DELIBERATE"
        assert via == "regex"

    @pytest.mark.anyio()
    async def test_direct_command_does_not_deliberate(self) -> None:
        """Wave 61: a direct build command should NOT return DELIBERATE."""
        text = "Build me a CSV parser that handles quoted fields"

        intent, via = await parse_queen_intent(text, runtime=None)

        # Should either be None (no intent) or SPAWN — never DELIBERATE
        if intent is not None:
            assert intent["action"] != "DELIBERATE"


# ---------------------------------------------------------------------------
# Wave 62: DIRECT_WORK regex tests
# ---------------------------------------------------------------------------


class TestDirectWorkRegex:
    """Tests for the _DIRECT_WORK_RE pattern (Wave 62 Track 3)."""

    def test_where_is_matches(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("where is the budget enforcer defined?")

    def test_what_does_matches(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("what does the run_round method do?")

    def test_are_tests_matches(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("are the tests passing?")

    def test_show_me_matches(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("show me the colony manager code")

    def test_build_command_does_not_match(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("build a CSV parser") is None

    def test_git_status_matches(self) -> None:
        from formicos.adapters.queen_intent_parser import _DIRECT_WORK_RE

        assert _DIRECT_WORK_RE.search("git status of the repo")
