"""Credential scanning via detect-secrets with dual-config strategy (Wave 33 B1).

Two scanning configurations:
- Prose config: regex-only detectors (no entropy — Shannon entropy for English
  prose overlaps Base64 threshold at 4.5 bits, causing massive false positives).
- Code config: regex + entropy detectors (safe for code blocks).

detect-secrets has NO string-scanning API — must write to temp files and use
``scan_file()``. ``transient_settings`` modifies global state and is NOT
thread-safe — use only from the main asyncio loop (no concurrent calls).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Plugin configurations
# ---------------------------------------------------------------------------

# Prose config: regex-only, no entropy
PROSE_PLUGINS: list[dict[str, Any]] = [
    {"name": "AWSKeyDetector"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "BasicAuthDetector"},
    {"name": "CloudantDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "IbmCloudIamDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "SlackDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "SquareOAuthDetector"},
    {"name": "StripeDetector"},
    {"name": "TwilioKeyDetector"},
]

# Code config: regex + entropy (safe for code blocks)
CODE_PLUGINS: list[dict[str, Any]] = [
    *PROSE_PLUGINS,
    {"name": "Base64HighEntropyString", "limit": 4.5},
    {"name": "HexHighEntropyString", "limit": 3.0},
]


# ---------------------------------------------------------------------------
# Feature flag: detect-secrets may not be installed
# ---------------------------------------------------------------------------

_ds_available = False
try:
    from detect_secrets import settings as _ds_settings  # pyright: ignore[reportMissingImports]
    from detect_secrets.core import scan as _ds_scan  # pyright: ignore[reportMissingImports]

    _ds_available = True
except ImportError:
    _ds_scan = None  # type: ignore[assignment]
    _ds_settings = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

_RE_CODE_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _extract_code_blocks(text: str) -> list[tuple[str, int]]:
    """Extract fenced code blocks with their line offsets.

    Returns list of (block_text, starting_line_number_1based).
    """
    blocks: list[tuple[str, int]] = []
    for match in _RE_CODE_FENCE.finditer(text):
        start_line = text[: match.start()].count("\n") + 2  # +1 header, +1 for 1-based
        blocks.append((match.group(1), start_line))
    return blocks


def _deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate findings (same line + same type)."""
    seen: set[tuple[int, str]] = set()
    deduped: list[dict[str, Any]] = []
    for f in findings:
        key = (f.get("line_number", 0), f.get("type", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def scan_text(text: str, *, is_code: bool = False) -> list[dict[str, Any]]:
    """Scan text for credentials via detect-secrets.

    Returns list of findings with type, line_number, and secret_value.
    Falls back to empty list if detect-secrets is not installed.
    """
    if not _ds_available or not text.strip():
        return []

    plugins = CODE_PLUGINS if is_code else PROSE_PLUGINS
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8",
        ) as f:
            f.write(text)
            f.flush()
            tmp_path = f.name
        with _ds_settings.transient_settings({"plugins_used": plugins}):  # pyright: ignore[reportOptionalMemberAccess]
            secrets = _ds_scan.scan_file(tmp_path)  # pyright: ignore[reportOptionalMemberAccess]
        return [
            {
                "type": s.type,
                "line_number": s.line_number,
                "secret_value": s.secret_value,
            }
            for s in secrets
        ]
    except Exception:  # noqa: BLE001
        log.debug("credential_scan.scan_failed")
        return []
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)


def scan_mixed_content(text: str) -> list[dict[str, Any]]:
    """Dual-config scan: prose config on full text, code config on code blocks."""
    if not text.strip():
        return []

    # Pass 1: regex-only on full text
    findings = scan_text(text, is_code=False)

    # Pass 2: extract code blocks and scan with entropy
    code_blocks = _extract_code_blocks(text)
    for block_text, line_offset in code_blocks:
        code_findings = scan_text(block_text, is_code=True)
        for f in code_findings:
            f["line_number"] += line_offset - 1
        findings.extend(code_findings)

    return _deduplicate_findings(findings)


def redact_credentials(text: str) -> tuple[str, int]:
    """Redact detected credentials in text.

    Returns (redacted_text, redaction_count).
    """
    findings = scan_mixed_content(text)
    if not findings:
        return text, 0

    lines = text.split("\n")
    count = 0
    # Sort by line number descending for safe in-place replacement
    for finding in sorted(findings, key=lambda f: f["line_number"], reverse=True):
        line_idx: int = int(finding["line_number"]) - 1
        secret: str = str(finding.get("secret_value", ""))
        if 0 <= line_idx < len(lines) and secret:
            lines[line_idx] = lines[line_idx].replace(
                secret,
                f"[REDACTED:{finding['type']}]",
            )
            count += 1

    return "\n".join(lines), count


__all__ = [
    "CODE_PLUGINS",
    "PROSE_PLUGINS",
    "redact_credentials",
    "scan_mixed_content",
    "scan_text",
]
