"""Tests for output sanitizer (Wave 32 C1b).

Covers ANSI stripping, truncation, and clean passthrough.
"""

from __future__ import annotations

from formicos.adapters.output_sanitizer import MAX_OUTPUT_CHARS, sanitize_output


class TestANSIStripping:
    """ANSI escape sequences should be removed."""

    def test_strips_color_codes(self) -> None:
        text = "\x1b[31mERROR\x1b[0m: something failed"
        result = sanitize_output(text)
        assert "\x1b" not in result
        assert "ERROR" in result
        assert "something failed" in result

    def test_strips_bold_and_underline(self) -> None:
        text = "\x1b[1mBold\x1b[0m and \x1b[4munderline\x1b[0m"
        result = sanitize_output(text)
        assert result == "Bold and underline"

    def test_strips_cursor_movement(self) -> None:
        text = "\x1b[2Jhello\x1b[1A"
        result = sanitize_output(text)
        assert "\x1b" not in result
        assert "hello" in result


class TestCleanPassthrough:
    """Normal text should be returned unchanged."""

    def test_plain_text_unchanged(self) -> None:
        text = "Hello, world! This is normal output."
        assert sanitize_output(text) == text

    def test_multiline_clean_text(self) -> None:
        text = "line 1\nline 2\nline 3"
        assert sanitize_output(text) == text

    def test_empty_string(self) -> None:
        assert sanitize_output("") == ""

    def test_unicode_preserved(self) -> None:
        text = "Hello 世界 🌍"
        assert sanitize_output(text) == text


class TestTruncation:
    """Output exceeding the limit should be truncated."""

    def test_long_output_truncated(self) -> None:
        text = "x" * (MAX_OUTPUT_CHARS + 500)
        result = sanitize_output(text)
        assert len(result) <= MAX_OUTPUT_CHARS + 50  # allow for suffix
        assert "[... output truncated]" in result

    def test_exact_limit_not_truncated(self) -> None:
        text = "x" * MAX_OUTPUT_CHARS
        result = sanitize_output(text)
        assert "[... output truncated]" not in result

    def test_below_limit_not_truncated(self) -> None:
        text = "x" * (MAX_OUTPUT_CHARS - 1)
        result = sanitize_output(text)
        assert result == text


class TestMixedContent:
    """Multi-line output with mixed content."""

    def test_multiline_with_ansi(self) -> None:
        text = "clean line\n\x1b[31mred error\x1b[0m\nanother clean line"
        result = sanitize_output(text)
        assert "clean line" in result
        assert "red error" in result
        assert "another clean line" in result
        assert "\x1b" not in result
