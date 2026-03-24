"""Wave 42 Team 2: extraction quality gating tests.

Tests cover:
- Conjunctive quality gate rules
- Empty content rejection
- Short + generic rejection
- Short + weak title + no domains rejection
- Generic + no domains + weak title rejection
- Useful concise entries survive
- Quality gate integration with extraction pipeline
"""

from __future__ import annotations

import pytest

from formicos.surface.colony_manager import _check_extraction_quality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    content: str = "A moderately long content string with details about the approach.",
    title: str = "Useful Pattern Title",
    summary: str = "A helpful summary of the technique.",
    entry_type: str = "skill",
    domains: list[str] | None = None,
) -> dict:
    return {
        "id": "test-entry-1",
        "content": content,
        "title": title,
        "summary": summary,
        "entry_type": entry_type,
        "domains": domains if domains is not None else ["python", "testing"],
    }


# ---------------------------------------------------------------------------
# Rule 1: empty content → always reject
# ---------------------------------------------------------------------------


class TestEmptyContentRejection:
    def test_empty_string(self) -> None:
        entry = _make_entry(content="")
        assert _check_extraction_quality(entry) == "empty_content"

    def test_whitespace_only(self) -> None:
        entry = _make_entry(content="   ")
        assert _check_extraction_quality(entry) == "empty_content"

    def test_very_short(self) -> None:
        entry = _make_entry(content="hi")
        assert _check_extraction_quality(entry) == "empty_content"

    def test_exactly_threshold(self) -> None:
        entry = _make_entry(content="abcde")
        # 5 chars is the minimum to not be "empty"
        assert _check_extraction_quality(entry) != "empty_content"


# ---------------------------------------------------------------------------
# Rule 2: short AND generic → reject
# ---------------------------------------------------------------------------


class TestShortAndGenericRejection:
    def test_short_and_generic(self) -> None:
        entry = _make_entry(
            content="Use best practice here.",
            title="Pattern",
        )
        assert _check_extraction_quality(entry) == "short_and_generic"

    def test_short_and_common_practice(self) -> None:
        entry = _make_entry(
            content="Common practice for this.",
            title="Approach",
        )
        assert _check_extraction_quality(entry) == "short_and_generic"

    def test_short_but_not_generic_passes(self) -> None:
        entry = _make_entry(
            content="Use asyncio.gather for parallel I/O",
            title="Async Pattern",
            domains=["python", "asyncio"],
        )
        # Short but specific — should pass
        assert _check_extraction_quality(entry) == ""

    def test_generic_but_not_short_passes(self) -> None:
        entry = _make_entry(
            content=(
                "This is a best practice for structuring your Python project. "
                "Organize modules by domain, keep imports clean, and separate concerns."
            ),
            title="Project Structure Convention",
        )
        # Generic phrase but long content — not rejected by this rule
        result = _check_extraction_quality(entry)
        assert result != "short_and_generic"


# ---------------------------------------------------------------------------
# Rule 3: short AND weak title AND no domains → reject
# ---------------------------------------------------------------------------


class TestShortWeakTitleNoDomains:
    def test_triple_conjunctive(self) -> None:
        entry = _make_entry(
            content="Some brief note here.",
            title="Note",
            domains=[],
        )
        assert _check_extraction_quality(entry) == "short_weak_title_no_domains"

    def test_short_weak_title_but_has_domains_passes(self) -> None:
        entry = _make_entry(
            content="Brief note about logging.",
            title="Note",
            domains=["python", "logging"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_short_no_domains_but_good_title_passes(self) -> None:
        entry = _make_entry(
            content="Brief note about this pattern.",
            title="Python Async Error Handling Pattern",
            domains=[],
        )
        # Title is long enough → not caught by this rule
        assert _check_extraction_quality(entry) != "short_weak_title_no_domains"


# ---------------------------------------------------------------------------
# Rule 4: generic AND no domains AND weak title → reject
# ---------------------------------------------------------------------------


class TestGenericNoDomainsWeakTitle:
    def test_triple_conjunctive(self) -> None:
        entry = _make_entry(
            content="This is the standard approach to solving the problem at hand. Nothing else.",
            title="Approach",
            domains=[],
        )
        assert _check_extraction_quality(entry) == "generic_no_domains_weak_title"

    def test_generic_no_domains_but_good_title_passes(self) -> None:
        entry = _make_entry(
            content="This is a standard approach to dependency injection in FastAPI.",
            title="FastAPI Dependency Injection Pattern",
            domains=[],
        )
        assert _check_extraction_quality(entry) != "generic_no_domains_weak_title"


# ---------------------------------------------------------------------------
# Useful entries survive
# ---------------------------------------------------------------------------


class TestUsefulEntriesSurvive:
    def test_normal_entry_passes(self) -> None:
        entry = _make_entry()
        assert _check_extraction_quality(entry) == ""

    def test_concise_but_specific_passes(self) -> None:
        entry = _make_entry(
            content="Use pytest.raises(ValueError) to assert exceptions.",
            title="Pytest Exception Testing",
            domains=["python", "pytest"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_short_with_good_title_and_domains_passes(self) -> None:
        entry = _make_entry(
            content="Always use UTC for timestamps.",
            title="UTC Timestamp Convention",
            domains=["python", "datetime"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_long_generic_with_domains_passes(self) -> None:
        entry = _make_entry(
            content=(
                "This is a well known pattern for handling configuration. "
                "Use environment variables for secrets and configuration files "
                "for non-sensitive defaults."
            ),
            title="Configuration Management",
            domains=["devops", "security"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_experience_entry_passes(self) -> None:
        entry = _make_entry(
            content="Discovered that aiosqlite requires explicit WAL mode on first connection.",
            title="aiosqlite WAL Initialization",
            entry_type="experience",
            domains=["python", "sqlite"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_bug_entry_passes(self) -> None:
        entry = _make_entry(
            content="Race condition in colony cleanup when two tasks finish simultaneously.",
            title="Colony Cleanup Race Condition",
            entry_type="bug",
            domains=["formicos", "concurrency"],
        )
        assert _check_extraction_quality(entry) == ""

    def test_anti_pattern_passes(self) -> None:
        entry = _make_entry(
            content="Do not use global mutable state for colony configuration.",
            title="Avoid Global Colony Config",
            entry_type="anti_pattern",
            domains=["formicos", "architecture"],
        )
        assert _check_extraction_quality(entry) == ""


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_missing_content_key(self) -> None:
        entry = {"id": "x", "title": "Title", "domains": ["a"]}
        assert _check_extraction_quality(entry) == "empty_content"

    def test_missing_title_key(self) -> None:
        entry = {
            "id": "x",
            "content": "Reasonable content string here for testing purposes.",
            "domains": ["python"],
        }
        assert _check_extraction_quality(entry) == ""

    def test_domains_with_empty_strings(self) -> None:
        entry = _make_entry(
            content="Short note here about nothing.",
            title="Note",
            domains=["", ""],
        )
        # Empty string domains treated as no domains
        assert _check_extraction_quality(entry) == "short_weak_title_no_domains"

    def test_case_insensitive_generic_detection(self) -> None:
        entry = _make_entry(
            content="Use BEST PRACTICE for coding.",
            title="Tip",
        )
        assert _check_extraction_quality(entry) == "short_and_generic"
