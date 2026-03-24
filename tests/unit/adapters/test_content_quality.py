"""Tests for Wave 44 content quality scoring."""

from __future__ import annotations

from formicos.adapters.content_quality import (
    ContentQualityResult,
    score_content,
)


# ---------------------------------------------------------------------------
# Basic scoring
# ---------------------------------------------------------------------------


class TestScoreContent:
    def test_empty_content_scores_zero(self) -> None:
        result = score_content("")
        assert result.score == 0.0
        assert "empty_content" in result.flags

    def test_whitespace_only_scores_zero(self) -> None:
        result = score_content("   \n\n  ")
        assert result.score == 0.0

    def test_good_article_scores_high(self) -> None:
        article = (
            "# Introduction to Python\n\n"
            "Python is a versatile programming language used for web development, "
            "data science, and automation. It features clear syntax and a rich "
            "standard library that makes development efficient.\n\n"
            "## Getting Started\n\n"
            "To begin programming in Python, you need to install the interpreter "
            "from the official website. The installation process is straightforward "
            "on all major operating systems.\n\n"
            "- Download the installer from python.org\n"
            "- Run the installation wizard\n"
            "- Verify with `python --version`\n\n"
            "## Core Concepts\n\n"
            "Python uses dynamic typing, which means variables do not need explicit "
            "type declarations. The language supports multiple programming paradigms "
            "including procedural, object-oriented, and functional programming.\n\n"
            "Functions are defined using the `def` keyword. Classes use the `class` "
            "keyword. Modules organize related code into separate files.\n"
        )
        result = score_content(article)
        assert result.score > 0.5

    def test_short_content_flagged(self) -> None:
        result = score_content("Hello world.")
        assert "very_short" in result.flags

    def test_spammy_content_flagged(self) -> None:
        spam = (
            "Buy now! Click here for a free trial! Limited time offer! "
            "Act now to get 100% free results! Make money from home! "
            "No risk guaranteed discount code available!"
        )
        result = score_content(spam)
        assert "spam_indicators" in result.flags
        assert result.signal_scores["spam_score"] < 0.7

    def test_repetitive_content_low_density(self) -> None:
        repetitive = ("the the the the the " * 50).strip()
        result = score_content(repetitive)
        assert result.signal_scores["information_density"] < 0.3


# ---------------------------------------------------------------------------
# Individual signals
# ---------------------------------------------------------------------------


class TestTextToMarkupRatio:
    def test_no_html_gives_neutral(self) -> None:
        result = score_content("Some text content", raw_html=None)
        assert result.signal_scores["text_to_markup"] == 0.7

    def test_high_ratio_scores_well(self) -> None:
        text = "Content " * 100
        html = f"<p>{text}</p>"
        result = score_content(text, raw_html=html)
        assert result.signal_scores["text_to_markup"] > 0.7

    def test_low_ratio_scores_poorly(self) -> None:
        text = "tiny"
        html = "<html><head>" + "<meta>" * 100 + "</head><body>tiny</body></html>"
        result = score_content(text, raw_html=html)
        assert result.signal_scores["text_to_markup"] < 0.3


class TestReadability:
    def test_well_structured_prose(self) -> None:
        prose = (
            "The algorithm processes each element in the array. "
            "It compares adjacent pairs and swaps them if needed. "
            "This process repeats until no more swaps are required. "
            "The time complexity is quadratic in the worst case. "
            "However, the best case is linear when already sorted."
        )
        result = score_content(prose)
        assert result.signal_scores["readability"] > 0.4


class TestStructuralQuality:
    def test_markdown_with_headings(self) -> None:
        structured = (
            "# Main Heading\n\n"
            "This is a paragraph of sufficient length to be counted as real content.\n\n"
            "## Sub Heading\n\n"
            "Another paragraph with enough text to be meaningful in the analysis.\n\n"
            "- List item one\n"
            "- List item two\n"
            "- List item three\n"
        )
        result = score_content(structured)
        assert result.signal_scores["structural_quality"] > 0.7


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


class TestResultShape:
    def test_all_signals_present(self) -> None:
        result = score_content("Some content text for testing the signals.")
        expected_signals = {
            "text_to_markup", "information_density", "readability",
            "structural_quality", "spam_score",
        }
        assert set(result.signal_scores.keys()) == expected_signals

    def test_score_bounded(self) -> None:
        result = score_content("Normal article content. " * 20)
        assert 0.0 <= result.score <= 1.0

    def test_word_count_accurate(self) -> None:
        result = score_content("one two three four five")
        assert result.word_count == 5

    def test_text_length_accurate(self) -> None:
        text = "Hello world"
        result = score_content(text)
        assert result.text_length == len(text)

    def test_result_is_frozen(self) -> None:
        result = score_content("test")
        assert isinstance(result, ContentQualityResult)
