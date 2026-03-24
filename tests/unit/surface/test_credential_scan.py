"""Tests for credential scanning via detect-secrets dual-config (Wave 33 B1)."""

from __future__ import annotations

import pytest

from formicos.surface.credential_scan import (
    _extract_code_blocks,
    redact_credentials,
    scan_mixed_content,
    scan_text,
)


class TestScanText:
    """Tests for scan_text (single-config scanning)."""

    def test_empty_text_returns_no_findings(self) -> None:
        assert scan_text("") == []
        assert scan_text("   ") == []

    def test_clean_prose_returns_no_findings(self) -> None:
        assert scan_text("This is a normal paragraph about Python.") == []


class TestExtractCodeBlocks:
    """Tests for _extract_code_blocks."""

    def test_single_code_block(self) -> None:
        text = "Some text\n```python\ncode here\n```\nMore text"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert "code here\n" in blocks[0][0]

    def test_no_code_blocks(self) -> None:
        text = "Just plain text with no code fences."
        assert _extract_code_blocks(text) == []

    def test_multiple_code_blocks(self) -> None:
        text = "```\nblock1\n```\nSome text\n```\nblock2\n```"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2


class TestScanMixedContent:
    """Tests for scan_mixed_content (dual-config)."""

    def test_empty_text(self) -> None:
        assert scan_mixed_content("") == []

    def test_clean_text_no_findings(self) -> None:
        assert scan_mixed_content("This is perfectly normal text.") == []


class TestRedactCredentials:
    """Tests for redact_credentials."""

    def test_no_secrets_returns_unchanged(self) -> None:
        text = "Hello world, no secrets here."
        redacted, count = redact_credentials(text)
        assert redacted == text
        assert count == 0

    def test_empty_text(self) -> None:
        redacted, count = redact_credentials("")
        assert redacted == ""
        assert count == 0


class TestDualConfig:
    """Tests verifying dual-config strategy: prose vs code."""

    def test_prose_config_excludes_entropy(self) -> None:
        """Prose scanning should NOT flag high-entropy strings that aren't
        known secret patterns (entropy detectors are code-only)."""
        # A random-looking but non-secret string
        text = "The result was aGVsbG8gd29ybGQ= which looked like base64"
        findings = scan_text(text, is_code=False)
        # Prose config has no entropy detectors, so this shouldn't match
        # unless it matches a known secret regex pattern
        # (base64 alone is not a known secret pattern without entropy detector)
        assert len(findings) == 0 or all(
            f["type"] != "Base64 High Entropy String" for f in findings
        )
