"""Tests for AI Filesystem (ADR-052) — Wave 77 Track B."""

from __future__ import annotations

from pathlib import Path

from formicos.surface.ai_filesystem import (
    parse_retry_of,
    promote_to_artifact,
    read_reflection,
    read_working_memory,
    write_reflection,
    write_working_note,
)
from formicos.surface.queen_budget import (
    _FALLBACKS,
    _FRACTIONS,
    FALLBACK_BUDGET,
    compute_queen_budget,
)

# ---------------------------------------------------------------------------
# parse_retry_of
# ---------------------------------------------------------------------------


class TestParseRetryOf:
    def test_with_prefix(self) -> None:
        orig, clean = parse_retry_of("[retry_of:col-123] Do the thing")
        assert orig == "col-123"
        assert clean == "Do the thing"

    def test_without_prefix(self) -> None:
        orig, clean = parse_retry_of("Just a normal task")
        assert orig == ""
        assert clean == "Just a normal task"

    def test_malformed_no_bracket(self) -> None:
        orig, clean = parse_retry_of("[retry_of:col-123 missing bracket")
        assert orig == ""
        assert clean == "[retry_of:col-123 missing bracket"

    def test_empty_string(self) -> None:
        orig, clean = parse_retry_of("")
        assert orig == ""
        assert clean == ""

    def test_whitespace_stripped(self) -> None:
        orig, clean = parse_retry_of("[retry_of:x]   spaced out")
        assert orig == "x"
        assert clean == "spaced out"


# ---------------------------------------------------------------------------
# write_working_note
# ---------------------------------------------------------------------------


class TestWriteWorkingNote:
    def test_append_mode(self, tmp_path: Path) -> None:
        result = write_working_note(
            str(tmp_path), "ws1", "notes.md", "line1",
        )
        assert "notes.md" in result
        write_working_note(str(tmp_path), "ws1", "notes.md", "line2")
        path = Path(result)
        content = path.read_text(encoding="utf-8")
        assert "line1" in content
        assert "line2" in content

    def test_overwrite_mode(self, tmp_path: Path) -> None:
        write_working_note(
            str(tmp_path), "ws1", "notes.md", "old",
        )
        result = write_working_note(
            str(tmp_path), "ws1", "notes.md", "new", mode="overwrite",
        )
        content = Path(result).read_text(encoding="utf-8")
        assert content == "new"
        assert "old" not in content

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        result = write_working_note(
            str(tmp_path), "ws1", "../../../etc/passwd", "hack",
        )
        # Should strip traversal and use just "passwd"
        assert "passwd" in result
        assert ".." not in result

    def test_invalid_filename(self, tmp_path: Path) -> None:
        result = write_working_note(str(tmp_path), "ws1", "", "content")
        assert result == "Error: invalid filename"


# ---------------------------------------------------------------------------
# promote_to_artifact
# ---------------------------------------------------------------------------


class TestPromoteToArtifact:
    def test_promotes_file(self, tmp_path: Path) -> None:
        # Create a runtime file first
        write_working_note(
            str(tmp_path), "ws1", "report.md", "final report",
            mode="overwrite",
        )
        result = promote_to_artifact(str(tmp_path), "ws1", "report.md")
        assert "artifacts" in result
        assert "deliverables" in result
        dest = Path(result)
        assert dest.is_file()
        assert dest.read_text(encoding="utf-8") == "final report"

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = promote_to_artifact(str(tmp_path), "ws1", "nonexistent.md")
        assert result.startswith("Error:")

    def test_invalid_filename(self, tmp_path: Path) -> None:
        result = promote_to_artifact(str(tmp_path), "ws1", "")
        assert result == "Error: invalid filename"

    def test_custom_subdir(self, tmp_path: Path) -> None:
        write_working_note(
            str(tmp_path), "ws1", "data.json", '{"ok": true}',
            mode="overwrite",
        )
        result = promote_to_artifact(
            str(tmp_path), "ws1", "data.json", target_subdir="exports",
        )
        assert "exports" in result


# ---------------------------------------------------------------------------
# Reflection write/read
# ---------------------------------------------------------------------------


class TestReflection:
    def test_write_and_read(self, tmp_path: Path) -> None:
        path = write_reflection(
            str(tmp_path), "ws1", "col-fail-1",
            task="summarize docs",
            failure_reason="stall after 3 rounds",
            rounds_completed=3,
            quality=0.25,
            stall_count=2,
            strategy="stigmergic",
            castes="coder,reviewer",
        )
        assert "reflection.md" in path
        content = read_reflection(str(tmp_path), "ws1", "col-fail-1")
        assert "col-fail-1" in content
        assert "summarize docs" in content
        assert "stall after 3 rounds" in content
        assert "Rounds completed: 3" in content

    def test_read_missing(self, tmp_path: Path) -> None:
        content = read_reflection(str(tmp_path), "ws1", "nonexistent")
        assert content == ""

    def test_last_round_summary_included(self, tmp_path: Path) -> None:
        write_reflection(
            str(tmp_path), "ws1", "col-2",
            last_round_summary="tried approach X",
        )
        content = read_reflection(str(tmp_path), "ws1", "col-2")
        assert "tried approach X" in content

    def test_task_truncated_at_500(self, tmp_path: Path) -> None:
        long_task = "x" * 1000
        write_reflection(str(tmp_path), "ws1", "col-3", task=long_task)
        content = read_reflection(str(tmp_path), "ws1", "col-3")
        # Task line should be truncated
        task_line = [line for line in content.splitlines() if line.startswith("Task:")][0]
        assert len(task_line) < 600


# ---------------------------------------------------------------------------
# read_working_memory
# ---------------------------------------------------------------------------


class TestReadWorkingMemory:
    def test_empty_when_no_files(self, tmp_path: Path) -> None:
        result = read_working_memory(str(tmp_path), "ws1", 1000)
        assert result == ""

    def test_reads_queen_dir(self, tmp_path: Path) -> None:
        write_working_note(
            str(tmp_path), "ws1", "plan.md", "the plan",
            mode="overwrite",
        )
        result = read_working_memory(str(tmp_path), "ws1", 1000)
        assert "Working Memory" in result
        assert "the plan" in result

    def test_tail_biased_truncation(self, tmp_path: Path) -> None:
        # Write content that exceeds a small budget
        write_working_note(
            str(tmp_path), "ws1", "big.md",
            "A" * 500 + "TAIL_MARKER",
            mode="overwrite",
        )
        # Budget of 50 tokens = 200 chars
        result = read_working_memory(str(tmp_path), "ws1", 50)
        assert "truncated" in result
        assert "TAIL_MARKER" in result

    def test_reads_shared_dir(self, tmp_path: Path) -> None:
        # Create a shared file manually
        shared = (
            tmp_path / ".formicos" / "runtime" / "ws1" / "shared"
        )
        shared.mkdir(parents=True)
        (shared / "info.txt").write_text("shared data", encoding="utf-8")
        result = read_working_memory(str(tmp_path), "ws1", 1000)
        assert "shared data" in result

    def test_skips_unsupported_extensions(self, tmp_path: Path) -> None:
        queen = tmp_path / ".formicos" / "runtime" / "ws1" / "queen"
        queen.mkdir(parents=True)
        (queen / "data.py").write_text("import os", encoding="utf-8")
        result = read_working_memory(str(tmp_path), "ws1", 1000)
        assert result == ""


# ---------------------------------------------------------------------------
# Budget slot: working_memory in QueenContextBudget
# ---------------------------------------------------------------------------


class TestBudgetSlot:
    def test_fractions_sum_to_one(self) -> None:
        total = sum(_FRACTIONS.values())
        assert abs(total - 1.0) < 0.001, f"Fractions sum to {total}"

    def test_ten_slots(self) -> None:
        assert len(_FRACTIONS) == 10
        assert len(_FALLBACKS) == 10

    def test_working_memory_fraction(self) -> None:
        assert _FRACTIONS["working_memory"] == 0.05

    def test_working_memory_fallback(self) -> None:
        assert _FALLBACKS["working_memory"] == 400

    def test_fallback_budget_has_working_memory(self) -> None:
        assert FALLBACK_BUDGET.working_memory == 400

    def test_proportional_budget(self) -> None:
        budget = compute_queen_budget(200_000, 4096)
        assert budget.working_memory >= 400
        # 5% of (200000 - 4096) = 9795
        assert budget.working_memory > 5000

    def test_none_context_returns_fallback(self) -> None:
        budget = compute_queen_budget(None, 4096)
        assert budget is FALLBACK_BUDGET
