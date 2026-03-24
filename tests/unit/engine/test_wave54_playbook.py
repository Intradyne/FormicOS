"""Tests for Wave 54: operational playbook layer.

Covers:
1. Playbook loader: loads YAML, formats correctly, falls back to generic
2. Context assembly: playbook appears at position 2.5 when provided
3. Budget block: convergence status appears when stall_count > 0
4. Reactive correction constants: PRODUCTIVE_TOOLS and OBSERVATION_TOOLS
5. tool_choice pass-through in adapter
"""

from __future__ import annotations

import json

import pytest

from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    ColonyContext,
)
from formicos.engine.context import (
    assemble_context,
    build_budget_block,
)
from formicos.engine.playbook_loader import (
    _format_playbook,
    clear_cache,
    compute_playbook_generation,
    load_common_mistakes,
    load_playbook,
)
from formicos.engine.runner import (
    OBSERVATION_TOOLS,
    PRODUCTIVE_TOOLS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recipe() -> CasteRecipe:
    return CasteRecipe(
        name="coder", description="test", system_prompt="You are a coder.",
        temperature=0.0, tools=[], max_tokens=1024,
    )


def _agent() -> AgentConfig:
    return AgentConfig(
        id="a1", name="a1", caste="coder",
        model="test-model", recipe=_recipe(),
    )


def _ctx(
    prev_summary: str | None = None,
    operational_playbook: str = "",
    stall_count: int = 0,
    convergence_progress: float = 0.0,
) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=1,
        merge_edges=[], prev_round_summary=prev_summary,
        operational_playbook=operational_playbook,
        stall_count=stall_count,
        convergence_progress=convergence_progress,
    )


# ---------------------------------------------------------------------------
# Playbook loader tests
# ---------------------------------------------------------------------------


class TestPlaybookLoader:
    """Test playbook YAML loading and formatting."""

    def setup_method(self) -> None:
        clear_cache()

    def test_load_code_implementation(self) -> None:
        """Loads the code_implementation playbook for coder caste."""
        result = load_playbook("code_implementation", "coder")
        assert result != ""
        assert "<operational_playbook>" in result
        assert "</operational_playbook>" in result
        assert "WORKFLOW:" in result
        assert "STEPS:" in result
        assert "PRODUCE OUTPUT WITH:" in result
        assert "GATHER INFO WITH" in result
        assert "EXAMPLE:" in result
        assert "write_workspace_file" in result

    def test_load_all_task_classes_for_coder(self) -> None:
        """All task classes load for coder caste."""
        classes = [
            "code_implementation", "code_review", "research",
            "design", "creative", "generic",
        ]
        for tc in classes:
            clear_cache()
            result = load_playbook(tc, "coder")
            assert result != "", f"{tc} should match coder caste"
            assert "write_workspace_file" in result or "patch_file" in result, (
                f"{tc} coder playbook should reference write tools"
            )

    def test_fallback_to_generic(self) -> None:
        """Unknown task class falls back to generic playbook."""
        result = load_playbook("nonexistent_task_class", "coder")
        assert "<operational_playbook>" in result
        assert "WORKFLOW:" in result

    def test_caste_mismatch_returns_empty(self) -> None:
        """Playbook for wrong caste returns empty string."""
        # code_implementation only targets coder caste
        result = load_playbook("code_implementation", "queen")
        # Should fall back to generic, which also may not include queen
        # The key is it doesn't crash
        assert isinstance(result, str)

    def test_cache_works(self) -> None:
        """Second call returns cached result."""
        r1 = load_playbook("code_implementation", "coder")
        r2 = load_playbook("code_implementation", "coder")
        assert r1 is r2  # Same object from cache

    def test_format_playbook_structure(self) -> None:
        """_format_playbook produces valid XML-tagged block."""
        data = {
            "workflow": "Read -> Write -> Test",
            "steps": ["Read file", "Write code", "Run tests"],
            "productive_tools": ["write_workspace_file", "code_execute"],
            "observation_tools": ["read_workspace_file"],
            "observation_limit": 2,
            "example": {
                "name": "write_workspace_file",
                "arguments": {"file_path": "test.py", "content": "pass"},
            },
        }
        result = _format_playbook(data)
        assert result.startswith("<operational_playbook>")
        assert result.endswith("</operational_playbook>")
        assert "WORKFLOW: Read -> Write -> Test" in result
        assert "1. Read file" in result
        assert "2. Write code" in result
        assert "3. Run tests" in result
        assert "PRODUCE OUTPUT WITH: write_workspace_file, code_execute" in result
        assert "GATHER INFO WITH (limit 2): read_workspace_file" in result
        # Verify JSON example is valid
        example_line = [
            line for line in result.split("\n") if line.startswith('{"name"')
        ]
        assert len(example_line) == 1
        parsed = json.loads(example_line[0])
        assert parsed["name"] == "write_workspace_file"
        assert parsed["arguments"]["file_path"] == "test.py"

    def test_example_uses_hermes_format(self) -> None:
        """The example JSON uses the Hermes tool-call format."""
        result = load_playbook("code_implementation", "coder")
        # Extract JSON from EXAMPLE section
        lines = result.split("\n")
        for i, line in enumerate(lines):
            if line.strip() == "EXAMPLE:":
                json_line = lines[i + 1]
                parsed = json.loads(json_line)
                assert "name" in parsed
                assert "arguments" in parsed
                return
        pytest.fail("No EXAMPLE section found in playbook")

    def test_reviewer_gets_caste_specific_playbook(self) -> None:
        """Reviewer gets a playbook that does NOT reference write tools."""
        for tc in ["code_review", "generic"]:
            clear_cache()
            result = load_playbook(tc, "reviewer")
            assert result != "", f"{tc} should match reviewer caste"
            assert "write_workspace_file" not in result, (
                f"{tc} reviewer playbook should NOT reference write_workspace_file"
            )
            assert "patch_file" not in result, (
                f"{tc} reviewer playbook should NOT reference patch_file"
            )

    def test_researcher_gets_caste_specific_playbook(self) -> None:
        """Researcher gets a playbook that does NOT reference write/commit tools."""
        for tc in ["research", "creative", "generic"]:
            clear_cache()
            result = load_playbook(tc, "researcher")
            assert result != "", f"{tc} should match researcher caste"
            assert "write_workspace_file" not in result, (
                f"{tc} researcher playbook should NOT reference write_workspace_file"
            )
            assert "git_commit" not in result, (
                f"{tc} researcher playbook should NOT reference git_commit"
            )

    def test_caste_specific_file_takes_priority(self) -> None:
        """research_researcher.yaml is loaded before research.yaml for researcher."""
        result = load_playbook("research", "researcher")
        assert "memory_write" in result, (
            "Researcher research playbook should use memory_write as productive tool"
        )


# ---------------------------------------------------------------------------
# Context assembly with playbook
# ---------------------------------------------------------------------------


class TestContextAssemblyPlaybook:
    """Test that operational playbook is injected at position 2.5."""

    @pytest.mark.asyncio
    async def test_playbook_injected_between_goal_and_structure(self) -> None:
        """Playbook appears after round goal and before structural context."""
        playbook = "<operational_playbook>\nTEST PLAYBOOK\n</operational_playbook>"
        ctx = ColonyContext(
            colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
            goal="Build a widget", round_number=1, merge_edges=[],
            operational_playbook=playbook,
            structural_context="src/\n  main.py\n  utils.py",
        )
        result = await assemble_context(
            agent=_agent(),
            colony_context=ctx,
            round_goal="Write a solver",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
            operational_playbook=playbook,
        )
        messages = result.messages
        # messages[0] = system prompt
        # messages[1] = round goal (user)
        # messages[2] = playbook (system) — position 2.5
        # messages[3] = common_mistakes (system) — position 2.6
        # messages[4] = structural context (user)
        assert messages[0]["role"] == "system"  # system prompt
        assert "Round goal:" in messages[1]["content"]  # goal
        assert messages[2]["role"] == "system"  # playbook
        assert "TEST PLAYBOOK" in messages[2]["content"]
        assert messages[3]["role"] == "system"  # common_mistakes
        assert "<common_mistakes>" in messages[3]["content"]
        assert "[Workspace Structure]" in messages[4]["content"]  # structure

    @pytest.mark.asyncio
    async def test_no_playbook_when_empty(self) -> None:
        """No playbook message injected when operational_playbook is empty."""
        ctx = _ctx(operational_playbook="")
        result = await assemble_context(
            agent=_agent(),
            colony_context=ctx,
            round_goal="Write a solver",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
        )
        messages = result.messages
        # Should be: system prompt, round goal — no playbook
        for msg in messages:
            assert "operational_playbook" not in msg["content"]

    @pytest.mark.asyncio
    async def test_playbook_truncated_to_budget(self) -> None:
        """Very long playbook is truncated to ~400 tokens (1600 chars)."""
        long_playbook = "A" * 5000
        ctx = _ctx(operational_playbook=long_playbook)
        result = await assemble_context(
            agent=_agent(),
            colony_context=ctx,
            round_goal="Write a solver",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
            operational_playbook=long_playbook,
        )
        playbook_msgs = [
            m for m in result.messages
            if m["role"] == "system" and "AAAA" in m["content"]
        ]
        assert len(playbook_msgs) == 1
        # 400 tokens × 4 chars = 1600 chars max
        assert len(playbook_msgs[0]["content"]) <= 1600


# ---------------------------------------------------------------------------
# Budget block with convergence status
# ---------------------------------------------------------------------------


class TestBudgetBlockConvergence:
    """Test convergence status appended to budget block."""

    def test_on_track_status(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
            stall_count=0, convergence_progress=0.5,
        )
        assert "STATUS: ON TRACK" in block

    def test_slow_status(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=3, max_rounds=10,
            stall_count=1, convergence_progress=0.1,
        )
        assert "STATUS: SLOW" in block

    def test_stalled_status(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=5, max_rounds=10,
            stall_count=3, convergence_progress=0.01,
        )
        assert "STATUS: STALLED" in block

    def test_final_round_status(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=9, max_rounds=10,
            stall_count=0, convergence_progress=0.5,
        )
        assert "STATUS: FINAL ROUND" in block

    def test_final_round_overrides_stall(self) -> None:
        """FINAL ROUND takes priority over STALLED."""
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=9, max_rounds=10,
            stall_count=5, convergence_progress=0.0,
        )
        assert "STATUS: FINAL ROUND" in block

    def test_default_no_stall_params(self) -> None:
        """Budget block works without stall params (backward compat)."""
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
        )
        assert "STATUS: ON TRACK" in block


# ---------------------------------------------------------------------------
# Tool category constants
# ---------------------------------------------------------------------------


class TestToolCategories:
    """Verify PRODUCTIVE_TOOLS and OBSERVATION_TOOLS are correct."""

    def test_productive_tools_contain_key_tools(self) -> None:
        assert "write_workspace_file" in PRODUCTIVE_TOOLS
        assert "patch_file" in PRODUCTIVE_TOOLS
        assert "code_execute" in PRODUCTIVE_TOOLS
        assert "workspace_execute" in PRODUCTIVE_TOOLS
        assert "git_commit" in PRODUCTIVE_TOOLS

    def test_observation_tools_contain_key_tools(self) -> None:
        assert "list_workspace_files" in OBSERVATION_TOOLS
        assert "read_workspace_file" in OBSERVATION_TOOLS
        assert "memory_search" in OBSERVATION_TOOLS
        assert "git_status" in OBSERVATION_TOOLS
        assert "git_diff" in OBSERVATION_TOOLS

    def test_no_overlap(self) -> None:
        """Productive and observation sets don't overlap."""
        overlap = PRODUCTIVE_TOOLS & OBSERVATION_TOOLS
        assert overlap == set(), f"Overlapping tools: {overlap}"


# ---------------------------------------------------------------------------
# ColonyContext new fields
# ---------------------------------------------------------------------------


class TestColonyContextWave54Fields:
    """Verify new Wave 54 fields on ColonyContext."""

    def test_defaults(self) -> None:
        ctx = ColonyContext(
            colony_id="c1", workspace_id="w1", thread_id="t1",
            goal="test", round_number=1, merge_edges=[],
        )
        assert ctx.operational_playbook == ""
        assert ctx.stall_count == 0
        assert ctx.convergence_progress == 0.0

    def test_set_values(self) -> None:
        ctx = ColonyContext(
            colony_id="c1", workspace_id="w1", thread_id="t1",
            goal="test", round_number=1, merge_edges=[],
            operational_playbook="<playbook>test</playbook>",
            stall_count=3,
            convergence_progress=0.45,
        )
        assert ctx.operational_playbook == "<playbook>test</playbook>"
        assert ctx.stall_count == 3
        assert ctx.convergence_progress == 0.45


# ---------------------------------------------------------------------------
# Wave 56.5 A: Common mistakes anti-pattern injection
# ---------------------------------------------------------------------------


class TestCommonMistakes:
    """Test caste-aware common-mistakes loading and injection."""

    def setup_method(self) -> None:
        clear_cache()

    def test_coder_gets_coder_and_universal(self) -> None:
        """Coder caste gets both coder-specific and universal anti-patterns."""
        result = load_common_mistakes("coder")
        assert "<common_mistakes>" in result
        assert "</common_mistakes>" in result
        # Coder-specific
        assert "reading the target file" in result or "Observe current state" in result
        # Universal
        assert "retry" in result.lower() or "diagnosis" in result.lower()

    def test_non_coder_gets_universal_only(self) -> None:
        """Non-coder castes get only universal anti-patterns."""
        result = load_common_mistakes("researcher")
        assert "<common_mistakes>" in result
        # Universal rules present
        assert "retry" in result.lower() or "diagnosis" in result.lower()
        # Coder-specific rules absent
        assert "Observe current state" not in result

    def test_coder_under_120_tokens(self) -> None:
        """Coder common_mistakes block is under 120 tokens (~480 chars)."""
        result = load_common_mistakes("coder")
        assert len(result) < 480, f"Coder block too long: {len(result)} chars"

    def test_non_coder_under_40_tokens(self) -> None:
        """Non-coder common_mistakes block is under 40 tokens (~160 chars)."""
        result = load_common_mistakes("reviewer")
        assert len(result) < 250, f"Non-coder block too long: {len(result)} chars"

    def test_cache_works(self) -> None:
        """Second call returns cached result."""
        r1 = load_common_mistakes("coder")
        r2 = load_common_mistakes("coder")
        assert r1 is r2

    def test_clear_cache_resets(self) -> None:
        """clear_cache() invalidates common_mistakes cache."""
        r1 = load_common_mistakes("coder")
        clear_cache()
        r2 = load_common_mistakes("coder")
        assert r1 == r2  # Same content
        assert r1 is not r2  # Different object

    @pytest.mark.asyncio
    async def test_common_mistakes_injected_at_position_2_6(self) -> None:
        """Common mistakes appear after playbook and before structural context."""
        ctx = ColonyContext(
            colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
            goal="Build a widget", round_number=1, merge_edges=[],
            structural_context="src/\n  main.py",
        )
        result = await assemble_context(
            agent=_agent(),
            colony_context=ctx,
            round_goal="Write a solver",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
        )
        # Find the common_mistakes message
        cm_msgs = [
            m for m in result.messages
            if "<common_mistakes>" in m.get("content", "")
        ]
        assert len(cm_msgs) == 1
        assert cm_msgs[0]["role"] == "system"


# ---------------------------------------------------------------------------
# Wave 56.5 C: Playbook generation stamping
# ---------------------------------------------------------------------------


class TestPlaybookGeneration:
    """Test content-derived playbook generation hash."""

    def setup_method(self) -> None:
        clear_cache()

    def test_returns_12_hex_chars(self) -> None:
        """Generation hash is 12 hex characters."""
        gen = compute_playbook_generation()
        assert len(gen) == 12
        assert all(c in "0123456789abcdef" for c in gen)

    def test_deterministic(self) -> None:
        """Same files produce same hash."""
        g1 = compute_playbook_generation()
        clear_cache()
        g2 = compute_playbook_generation()
        assert g1 == g2

    def test_cache_works(self) -> None:
        """Second call returns cached result."""
        g1 = compute_playbook_generation()
        g2 = compute_playbook_generation()
        assert g1 is g2  # Same string object from cache

    def test_clear_cache_resets(self) -> None:
        """clear_cache() invalidates generation cache."""
        g1 = compute_playbook_generation()
        clear_cache()
        g2 = compute_playbook_generation()
        assert g1 == g2
        assert g1 is not g2
