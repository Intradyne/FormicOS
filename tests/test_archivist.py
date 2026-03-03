"""
Tests for FormicOS v0.6.0 Archivist.

Covers:
  1.  summarize_round returns valid Episode
  2.  summarize_round handles LLM failure gracefully
  3.  compress_epoch returns valid EpochSummary
  4.  compress_epoch with empty episodes
  5.  maybe_compress_epochs triggers when enough episodes
  6.  maybe_compress_epochs skips when too few episodes
  7.  extract_tkg_tuples returns valid TKGTuple list
  8.  extract_tkg_tuples handles malformed JSON with repair
  9.  distill_skills returns categorized Skill list
  10. scan_repository walks dirs and returns summaries
  11. scan_repository skips unreadable files
  12. scan_repository uses content hash cache
  13. harvest_knowledge calls both distill and scan
  14. JSON repair fallback on bad LLM output
  15. Retry on LLM timeout
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.archivist import Archivist, _parse_json_response
from src.models import (
    Episode,
    EpochSummary,
    FormicOSConfig,
    Skill,
    SkillTier,
    TKGTuple,
)


# =========================================================================
# Helpers
# =========================================================================


def _make_config(**overrides: Any) -> FormicOSConfig:
    """Build a minimal FormicOSConfig for Archivist tests."""
    raw = {
        "schema_version": "0.6.0",
        "identity": {"name": "FormicOS", "version": "0.6.0"},
        "hardware": {"gpu": "test", "vram_gb": 32, "vram_alert_threshold_gb": 28},
        "inference": {
            "endpoint": "http://localhost:8080/v1",
            "model": "test-model",
            "model_alias": "gpt-4",
            "max_tokens_per_agent": 5000,
            "temperature": 0,
            "timeout_seconds": 120,
            "context_size": 32768,
        },
        "embedding": {
            "model": "test-embed",
            "endpoint": "http://localhost:8081/v1",
            "dimensions": 1024,
            "max_tokens": 8192,
            "batch_size": 32,
            "routing_model": "all-MiniLM-L6-v2",
        },
        "routing": {"tau": 0.35, "k_in": 3, "broadcast_fallback": True},
        "convergence": {
            "similarity_threshold": 0.95,
            "rounds_before_force_halt": 2,
            "path_diversity_warning_after": 3,
        },
        "summarization": {
            "epoch_window": 5,
            "max_epoch_tokens": 400,
            "max_agent_summary_tokens": 200,
            "tree_sitter_languages": ["python"],
        },
        "temporal": {
            "episodic_ttl_hours": 72,
            "stall_repeat_threshold": 3,
            "stall_window_minutes": 20,
            "tkg_max_tuples": 5000,
        },
        "castes": {
            "manager": {
                "system_prompt_file": "manager.md",
                "tools": [],
                "model_override": None,
            },
        },
        "persistence": {
            "session_dir": ".formicos/sessions",
            "autosave_interval_seconds": 30,
        },
        "approval_required": [],
        "qdrant": {
            "host": "localhost",
            "port": 6333,
            "grpc_port": 6334,
            "collections": {
                "project_docs": {"embedding": "bge-m3", "dimensions": 1024},
            },
        },
        "mcp_gateway": {
            "enabled": False,
            "transport": "stdio",
            "command": "docker",
            "args": ["mcp", "gateway", "run"],
            "docker_fallback_endpoint": "http://localhost:8811",
            "sse_retry_attempts": 5,
            "sse_retry_delay_seconds": 3,
        },
        "model_registry": {
            "test/model": {
                "backend": "llama_cpp",
                "endpoint": "http://localhost:8080/v1",
                "context_length": 32768,
                "vram_gb": 25.6,
                "supports_tools": True,
                "supports_streaming": True,
            },
        },
        "skill_bank": {
            "storage_file": ".formicos/skill_bank.json",
            "retrieval_top_k": 3,
            "dedup_threshold": 0.85,
            "evolution_interval": 5,
            "prune_zero_hit_after": 10,
        },
        "subcaste_map": {
            "heavy": {"primary": "test/model"},
            "balanced": {"primary": "test/model"},
            "light": {"primary": "test/model"},
        },
        "teams": {
            "max_teams_per_colony": 4,
            "team_summary_max_tokens": 200,
            "allow_dynamic_spawn": True,
        },
        "colonies": {},
    }
    raw.update(overrides)
    return FormicOSConfig.model_validate(raw)


def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_client(content: str = "mock summary") -> AsyncMock:
    """Build a mock AsyncOpenAI client that returns a fixed string."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response(content)
    )
    return client


def _make_archivist(
    content: str = "mock summary",
    client: AsyncMock | None = None,
    **config_overrides: Any,
) -> tuple[Archivist, AsyncMock]:
    """Build an Archivist with a mock client for testing."""
    if client is None:
        client = _make_client(content)
    config = _make_config(**config_overrides)
    archivist = Archivist(
        model_client=client,
        model_name="test-model",
        config=config,
    )
    return archivist, client


# =========================================================================
# Mock context tree for maybe_compress_epochs tests
# =========================================================================


class FakeContextTree:
    """Minimal stub of AsyncContextTree for testing."""

    def __init__(
        self,
        episodes: list[Episode] | None = None,
        epoch_summaries: list[EpochSummary] | None = None,
    ):
        self._episodes = episodes or []
        self._epoch_summaries = epoch_summaries or []
        self._recorded_epochs: list[EpochSummary] = []

    def get_episodes(self, window: int | None = None) -> list[Episode]:
        if window is None:
            return list(self._episodes)
        return list(self._episodes[-window:])

    def get_epoch_summaries(self) -> list[EpochSummary]:
        return list(self._epoch_summaries)

    async def record_epoch_summary(self, summary: EpochSummary) -> None:
        self._epoch_summaries.append(summary)
        self._recorded_epochs.append(summary)


# =========================================================================
# 1. summarize_round returns valid Episode
# =========================================================================


@pytest.mark.asyncio
async def test_summarize_round_returns_valid_episode():
    """summarize_round should return a properly structured Episode."""
    archivist, client = _make_archivist(content="Round 1 went well.")

    episode = await archivist.summarize_round(
        round_num=1,
        goal="Implement auth module",
        agent_outputs={"coder_01": "Wrote auth.py", "reviewer_01": "LGTM"},
    )

    assert isinstance(episode, Episode)
    assert episode.round_num == 1
    assert episode.goal == "Implement auth module"
    assert episode.summary == "Round 1 went well."
    assert "coder_01" in episode.agent_outputs
    assert "reviewer_01" in episode.agent_outputs
    client.chat.completions.create.assert_awaited_once()


# =========================================================================
# 2. summarize_round handles LLM failure gracefully
# =========================================================================


@pytest.mark.asyncio
async def test_summarize_round_handles_llm_failure():
    """When the LLM call fails, summarize_round still returns an Episode
    with an error-note summary instead of crashing."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("LLM unavailable")
    )
    archivist, _ = _make_archivist(client=client)

    episode = await archivist.summarize_round(
        round_num=3,
        goal="Fix tests",
        agent_outputs={"coder_01": "attempted fix"},
    )

    assert isinstance(episode, Episode)
    assert episode.round_num == 3
    assert "failed" in episode.summary.lower() or "Summarization failed" in episode.summary
    assert episode.goal == "Fix tests"


# =========================================================================
# 3. compress_epoch returns valid EpochSummary
# =========================================================================


@pytest.mark.asyncio
async def test_compress_epoch_returns_valid_epoch_summary():
    """compress_epoch should return a well-formed EpochSummary."""
    archivist, client = _make_archivist(
        content="Epochs 1-5: steady progress on auth module."
    )

    episodes = [
        Episode(round_num=i, summary=f"Round {i} summary", goal=f"goal_{i}")
        for i in range(1, 6)
    ]

    epoch = await archivist.compress_epoch(episodes, epoch_id=1)

    assert isinstance(epoch, EpochSummary)
    assert epoch.epoch_id == 1
    assert epoch.round_range == (1, 5)
    assert "progress" in epoch.summary
    client.chat.completions.create.assert_awaited_once()


# =========================================================================
# 4. compress_epoch with empty episodes
# =========================================================================


@pytest.mark.asyncio
async def test_compress_epoch_with_empty_episodes():
    """compress_epoch with an empty list should return a placeholder epoch."""
    archivist, client = _make_archivist()

    epoch = await archivist.compress_epoch([], epoch_id=0)

    assert isinstance(epoch, EpochSummary)
    assert epoch.epoch_id == 0
    assert "empty" in epoch.summary.lower() or "Empty" in epoch.summary
    # No LLM call should be made for empty episodes
    client.chat.completions.create.assert_not_awaited()


# =========================================================================
# 5. maybe_compress_epochs triggers when enough episodes
# =========================================================================


@pytest.mark.asyncio
async def test_maybe_compress_epochs_triggers():
    """When episodes >= epoch_window, maybe_compress_epochs should
    compress and record an EpochSummary."""
    archivist, _ = _make_archivist(content="Compressed epoch summary.")

    episodes = [
        Episode(round_num=i, summary=f"Round {i}", goal=f"goal_{i}")
        for i in range(1, 6)  # 5 episodes = epoch_window
    ]
    ctx = FakeContextTree(episodes=episodes)

    compressed = await archivist.maybe_compress_epochs(ctx)

    assert compressed is True
    assert len(ctx._recorded_epochs) == 1
    assert ctx._recorded_epochs[0].epoch_id == 1
    assert ctx._recorded_epochs[0].round_range == (1, 5)


# =========================================================================
# 6. maybe_compress_epochs skips when too few episodes
# =========================================================================


@pytest.mark.asyncio
async def test_maybe_compress_epochs_skips_when_too_few():
    """When episodes < epoch_window, no compression should occur."""
    archivist, client = _make_archivist()

    episodes = [
        Episode(round_num=i, summary=f"Round {i}", goal=f"goal_{i}")
        for i in range(1, 4)  # Only 3 episodes, window is 5
    ]
    ctx = FakeContextTree(episodes=episodes)

    compressed = await archivist.maybe_compress_epochs(ctx)

    assert compressed is False
    assert len(ctx._recorded_epochs) == 0
    client.chat.completions.create.assert_not_awaited()


# =========================================================================
# 7. extract_tkg_tuples returns valid TKGTuple list
# =========================================================================


@pytest.mark.asyncio
async def test_extract_tkg_tuples_returns_valid_list():
    """extract_tkg_tuples should parse LLM JSON into TKGTuple objects."""
    tkg_json = json.dumps([
        {"subject": "coder_01", "predicate": "Modified_File", "object": "auth.py"},
        {"subject": "reviewer_01", "predicate": "Approved", "object": "auth.py"},
    ])
    archivist, _ = _make_archivist(content=tkg_json)

    tuples = await archivist.extract_tkg_tuples(
        round_num=2,
        agent_outputs={"coder_01": "Wrote auth.py", "reviewer_01": "LGTM"},
    )

    assert len(tuples) == 2
    assert all(isinstance(t, TKGTuple) for t in tuples)
    assert tuples[0].subject == "coder_01"
    assert tuples[0].predicate == "Modified_File"
    assert tuples[0].object_ == "auth.py"
    assert tuples[0].round_num == 2
    assert tuples[1].subject == "reviewer_01"


# =========================================================================
# 8. extract_tkg_tuples handles malformed JSON with repair
# =========================================================================


@pytest.mark.asyncio
async def test_extract_tkg_tuples_handles_malformed_json():
    """When the LLM returns malformed JSON, json_repair should fix it."""
    # Malformed: trailing comma, no closing bracket
    malformed = '[{"subject": "coder_01", "predicate": "Wrote", "object": "main.py",}]'
    archivist, _ = _make_archivist(content=malformed)

    tuples = await archivist.extract_tkg_tuples(
        round_num=1,
        agent_outputs={"coder_01": "Wrote main.py"},
    )

    # json_repair should handle the trailing comma
    assert len(tuples) == 1
    assert tuples[0].subject == "coder_01"
    assert tuples[0].object_ == "main.py"


# =========================================================================
# 9. distill_skills returns categorized Skill list
# =========================================================================


@pytest.mark.asyncio
async def test_distill_skills_returns_categorized_skills():
    """distill_skills should return Skills across all tiers."""
    llm_response = json.dumps({
        "general": [
            "Always run tests before declaring done",
            "Decompose complex tasks into subtasks",
        ],
        "task_specific": [
            {"category": "auth", "skill": "Validate redirect_uri against allowlist"},
        ],
        "lessons": [
            "Colonies stall at round 7 -- trigger compression at round 5",
        ],
    })
    archivist, _ = _make_archivist(content=llm_response)

    skills = await archivist.distill_skills(
        task="Implement OAuth2",
        outcome="completed",
        round_summaries="Round 1: set up. Round 2: implemented. Round 3: tested.",
    )

    assert isinstance(skills, list)
    assert all(isinstance(s, Skill) for s in skills)

    general = [s for s in skills if s.tier == SkillTier.GENERAL]
    task_specific = [s for s in skills if s.tier == SkillTier.TASK_SPECIFIC]
    lessons = [s for s in skills if s.tier == SkillTier.LESSON]

    assert len(general) == 2
    assert len(task_specific) == 1
    assert len(lessons) == 1

    assert task_specific[0].category == "auth"
    assert "redirect_uri" in task_specific[0].content


# =========================================================================
# 10. scan_repository walks dirs and returns summaries
# =========================================================================


@pytest.mark.asyncio
async def test_scan_repository_walks_dirs(tmp_path: Path):
    """scan_repository should find files, summarize, and return per-dir results."""
    # Create test directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def main(): pass", encoding="utf-8")
    (src_dir / "utils.py").write_text("def helper(): pass", encoding="utf-8")

    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "core.py").write_text("class Core: pass", encoding="utf-8")

    archivist, _ = _make_archivist(content="File handles core logic.")

    summaries = await archivist.scan_repository(
        repo_path=tmp_path, extensions=[".py"]
    )

    assert isinstance(summaries, dict)
    assert len(summaries) >= 2  # at least src/ and lib/

    # Verify directory paths are present
    dir_keys = list(summaries.keys())
    assert any("src" in k for k in dir_keys)
    assert any("lib" in k for k in dir_keys)


# =========================================================================
# 11. scan_repository skips unreadable files
# =========================================================================


@pytest.mark.asyncio
async def test_scan_repository_skips_unreadable_files(tmp_path: Path):
    """scan_repository should skip files that raise OSError and continue."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    good_file = src_dir / "good.py"
    good_file.write_text("x = 1", encoding="utf-8")
    bad_file = src_dir / "bad.py"
    bad_file.write_text("y = 2", encoding="utf-8")

    archivist, _ = _make_archivist(content="File summary.")

    # Patch read_text to fail for bad.py
    original_read_text = Path.read_text

    def patched_read_text(self, *args, **kwargs):
        if self.name == "bad.py":
            raise OSError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched_read_text):
        summaries = await archivist.scan_repository(
            repo_path=tmp_path, extensions=[".py"]
        )

    # Should still have results (from good.py)
    assert len(summaries) >= 1
    # The summary should contain the good file's result
    all_values = " ".join(summaries.values())
    assert "File summary" in all_values


# =========================================================================
# 12. scan_repository uses content hash cache
# =========================================================================


@pytest.mark.asyncio
async def test_scan_repository_uses_content_hash_cache(tmp_path: Path):
    """Second scan of unchanged files should hit cache, not call LLM again."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def main(): pass", encoding="utf-8")

    archivist, client = _make_archivist(content="Cached summary.")

    # First scan -- should call LLM
    summaries1 = await archivist.scan_repository(
        repo_path=tmp_path, extensions=[".py"]
    )
    call_count_1 = client.chat.completions.create.await_count
    assert call_count_1 >= 1

    # Second scan of same content -- should use cache
    summaries2 = await archivist.scan_repository(
        repo_path=tmp_path, extensions=[".py"]
    )
    call_count_2 = client.chat.completions.create.await_count

    assert call_count_2 == call_count_1, (
        "Second scan should not make additional LLM calls for cached content"
    )
    # Summaries should be the same
    assert summaries1 == summaries2


# =========================================================================
# 13. harvest_knowledge calls both distill and scan
# =========================================================================


@pytest.mark.asyncio
async def test_harvest_knowledge_returns_dict():
    """harvest_knowledge should return a dict with session_id, skills, etc."""
    skill_json = json.dumps({
        "general": ["Always validate input"],
        "task_specific": [],
        "lessons": [],
    })
    archivist, _ = _make_archivist(content=skill_json)

    result = await archivist.harvest_knowledge(
        session_id="sess_001",
        task="Build REST API",
        outcome="completed",
    )

    assert isinstance(result, dict)
    assert result["session_id"] == "sess_001"
    assert "skills" in result
    assert "repo_summaries" in result
    assert "timestamp" in result
    assert isinstance(result["skills"], list)


# =========================================================================
# 14. JSON repair fallback on bad LLM output
# =========================================================================


class TestJsonParseFallback:
    """Test the _parse_json_response helper."""

    def test_valid_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_repairable_json(self):
        # Trailing comma is repairable by json_repair
        result = _parse_json_response('{"key": "value",}')
        assert result is not None
        assert result.get("key") == "value"

    def test_completely_broken_json(self):
        result = _parse_json_response("this is not json at all", fallback=[])
        assert result == []

    def test_fallback_default_none(self):
        result = _parse_json_response("not json")
        assert result is None


@pytest.mark.asyncio
async def test_extract_tkg_tuples_totally_broken_json():
    """When LLM returns completely non-JSON text, return empty list."""
    archivist, _ = _make_archivist(
        content="I cannot extract any tuples from this."
    )

    tuples = await archivist.extract_tkg_tuples(
        round_num=1,
        agent_outputs={"coder_01": "did stuff"},
    )

    assert tuples == []


# =========================================================================
# 15. Retry on LLM timeout
# =========================================================================


@pytest.mark.asyncio
async def test_retry_on_llm_timeout():
    """The _llm_call method should retry once on failure before raising."""
    client = AsyncMock()
    # Fail first, succeed second
    client.chat.completions.create = AsyncMock(
        side_effect=[
            TimeoutError("LLM timed out"),
            _mock_llm_response("Success after retry"),
        ]
    )
    archivist, _ = _make_archivist(client=client)

    # _llm_call should succeed on the second attempt
    result = await archivist._llm_call("system", "user", max_tokens=100)

    assert result == "Success after retry"
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    """When both retry attempts fail, the error should propagate."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=TimeoutError("LLM timed out")
    )
    archivist, _ = _make_archivist(client=client)

    with pytest.raises(TimeoutError):
        await archivist._llm_call("system", "user", max_tokens=100)

    # Should have been called twice (initial + 1 retry)
    assert client.chat.completions.create.await_count == 2


# =========================================================================
# Additional edge cases
# =========================================================================


@pytest.mark.asyncio
async def test_maybe_compress_epochs_respects_existing_epochs():
    """When some episodes are already compressed into epochs, only the
    uncompressed remainder is considered."""
    archivist, _ = _make_archivist(content="Epoch 2 summary.")

    # Rounds 1-5 already compressed into epoch 1
    episodes = [
        Episode(round_num=i, summary=f"Round {i}", goal=f"goal_{i}")
        for i in range(1, 9)  # 8 episodes total
    ]
    existing_epoch = EpochSummary(
        epoch_id=1,
        summary="Epoch 1 summary",
        round_range=(1, 5),
    )
    ctx = FakeContextTree(
        episodes=episodes,
        epoch_summaries=[existing_epoch],
    )

    # Uncompressed: rounds 6, 7, 8 = only 3, less than window of 5
    compressed = await archivist.maybe_compress_epochs(ctx)
    assert compressed is False


@pytest.mark.asyncio
async def test_distill_skills_handles_llm_failure():
    """When the LLM call fails completely, distill_skills returns empty list."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("LLM down")
    )
    archivist, _ = _make_archivist(client=client)

    skills = await archivist.distill_skills(
        task="Build API",
        outcome="failed",
        round_summaries="Round 1: started. Round 2: crashed.",
    )

    assert skills == []


@pytest.mark.asyncio
async def test_extract_tkg_tuples_llm_failure_returns_empty():
    """When LLM fails during TKG extraction, return empty list."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("LLM unavailable")
    )
    archivist, _ = _make_archivist(client=client)

    tuples = await archivist.extract_tkg_tuples(
        round_num=1,
        agent_outputs={"coder_01": "stuff"},
    )

    assert tuples == []


@pytest.mark.asyncio
async def test_compress_epoch_handles_llm_failure():
    """When LLM fails during epoch compression, a fallback summary is used."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("LLM offline")
    )
    archivist, _ = _make_archivist(client=client)

    episodes = [
        Episode(round_num=1, summary="Round 1", goal="goal_1"),
        Episode(round_num=2, summary="Round 2", goal="goal_2"),
    ]

    epoch = await archivist.compress_epoch(episodes, epoch_id=1)

    assert isinstance(epoch, EpochSummary)
    assert epoch.epoch_id == 1
    assert "failed" in epoch.summary.lower() or "Compression failed" in epoch.summary
    assert epoch.round_range == (1, 2)
