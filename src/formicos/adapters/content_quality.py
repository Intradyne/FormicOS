"""Content-quality scoring without LLM calls (Wave 44).

Cheap heuristic scoring for fetched web content. Feeds the ``scanner``
dimension of the admission pipeline. All signals are O(n) in text length,
deterministic, and explainable.

Signals:
  1. text_to_markup_ratio — higher is better (content-dense pages)
  2. information_density — unique words / total words
  3. readability — sentence length distribution (Flesch-like proxy)
  4. structural_quality — heading/paragraph structure
  5. spam_indicators — SEO/spam keyword density

The composite score is [0.0, 1.0] — higher is more trustworthy.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Signal weights (sum to 1.0)
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "text_to_markup": 0.15,
    "information_density": 0.25,
    "readability": 0.20,
    "structural_quality": 0.15,
    "spam_score": 0.25,
}

# ---------------------------------------------------------------------------
# Spam / SEO indicators
# ---------------------------------------------------------------------------

_SPAM_PATTERNS: list[str] = [
    r"\bbuy now\b",
    r"\bclick here\b",
    r"\bfree trial\b",
    r"\blimited time\b",
    r"\bact now\b",
    r"\bsubscribe now\b",
    r"\bunsubscribe\b",
    r"\bcongratulations\b",
    r"\byou won\b",
    r"\b100% free\b",
    r"\bmake money\b",
    r"\bwork from home\b",
    r"\bguaranteed\b",
    r"\bno risk\b",
    r"\bdiscount code\b",
    r"\baffiliate\b",
    r"\bsponsored\b",
]

_SPAM_REGEXES = [re.compile(p, re.IGNORECASE) for p in _SPAM_PATTERNS]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentQualityResult:
    """Quality assessment of extracted content."""

    score: float  # composite [0.0, 1.0]
    signal_scores: dict[str, float]
    flags: list[str]
    text_length: int
    word_count: int


# ---------------------------------------------------------------------------
# Signal functions
# ---------------------------------------------------------------------------


def _score_text_to_markup(text: str, raw_html: str | None) -> float:
    """Score based on text-to-markup ratio. No HTML = 0.7 default."""
    if not raw_html or not text:
        return 0.7  # neutral when no HTML available

    text_len = len(text)
    html_len = len(raw_html)
    if html_len == 0:
        return 0.7

    ratio = text_len / html_len
    # Sigmoid-like mapping: ratio 0.0->0.0, 0.1->0.4, 0.3->0.7, 0.5+->0.9+
    return min(1.0, 1.0 - math.exp(-4.0 * ratio))


def _score_information_density(words: list[str]) -> float:
    """Unique words / total words. Higher diversity = more informative."""
    if len(words) < 10:
        return 0.0

    unique = len(set(w.lower() for w in words))
    total = len(words)
    ratio = unique / total

    # Most good content is 0.3-0.7 diversity. Normalize.
    if ratio < 0.15:
        return 0.1  # very repetitive
    if ratio > 0.8:
        return 0.7  # keyword-stuffed or very short
    # Linear map [0.15, 0.7] -> [0.3, 1.0]
    return min(1.0, 0.3 + (ratio - 0.15) * (0.7 / 0.55))


def _score_readability(text: str) -> float:
    """Sentence length distribution as readability proxy.

    Very short sentences = list/navigation junk.
    Very long sentences = machine-generated or poorly structured.
    Mixed medium-length = good.
    """
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

    if len(sentences) < 3:
        return 0.3  # too few sentences to judge

    lengths = [len(s.split()) for s in sentences]
    avg_len = sum(lengths) / len(lengths)
    variance = sum((sl - avg_len) ** 2 for sl in lengths) / len(lengths)
    std_dev = math.sqrt(variance)

    # Ideal: avg 12-25 words, moderate variance
    avg_score = 1.0
    if avg_len < 5:
        avg_score = 0.3
    elif avg_len < 8:
        avg_score = 0.6
    elif avg_len > 40:
        avg_score = 0.4
    elif avg_len > 30:
        avg_score = 0.6

    # Some variance is good (natural writing), too much is bad
    var_score = 1.0
    if std_dev < 2:
        var_score = 0.5  # monotonous
    elif std_dev > 20:
        var_score = 0.5  # chaotic

    return avg_score * 0.6 + var_score * 0.4


def _score_structural_quality(text: str) -> float:
    """Presence of headings, paragraphs, and structural markers."""
    lines = text.strip().splitlines()
    if len(lines) < 3:
        return 0.3

    heading_count = 0
    paragraph_count = 0
    list_item_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_count += 1
        elif stripped.startswith(("- ", "* ", "• ")):
            list_item_count += 1
        elif len(stripped) > 40:
            paragraph_count += 1

    # Well-structured content has some headings and paragraphs
    has_structure = heading_count > 0 or paragraph_count >= 3
    has_lists = list_item_count >= 2

    if has_structure and has_lists:
        return 0.95
    if has_structure:
        return 0.8
    if paragraph_count >= 2:
        return 0.6
    return 0.35


def _score_spam(text: str, words: list[str]) -> float:
    """Inverse spam score: 1.0 = no spam, 0.0 = full spam."""
    if not words:
        return 0.5

    spam_hits = sum(1 for regex in _SPAM_REGEXES if regex.search(text))
    spam_density = spam_hits / max(len(words) / 100, 1.0)

    # 0 hits = 1.0, 3+ hits per 100 words = near 0
    return max(0.0, 1.0 - spam_density * 0.33)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_content(
    text: str,
    *,
    raw_html: str | None = None,
) -> ContentQualityResult:
    """Score extracted content quality without LLM calls.

    Args:
        text: The extracted text to score.
        raw_html: The original HTML (if available) for markup-ratio signal.

    Returns:
        ContentQualityResult with composite score and per-signal breakdown.
    """
    if not text or not text.strip():
        return ContentQualityResult(
            score=0.0,
            signal_scores={k: 0.0 for k in _WEIGHTS},
            flags=["empty_content"],
            text_length=0,
            word_count=0,
        )

    words = text.split()
    word_count = len(words)

    # Compute individual signals
    signals: dict[str, float] = {
        "text_to_markup": _score_text_to_markup(text, raw_html),
        "information_density": _score_information_density(words),
        "readability": _score_readability(text),
        "structural_quality": _score_structural_quality(text),
        "spam_score": _score_spam(text, words),
    }

    # Weighted composite
    composite = sum(signals[k] * _WEIGHTS[k] for k in _WEIGHTS)

    # Flags
    flags: list[str] = []
    if word_count < 50:
        flags.append("very_short")
    if signals["spam_score"] < 0.5:
        flags.append("spam_indicators")
    if signals["information_density"] < 0.3:
        flags.append("low_diversity")
    if signals["readability"] < 0.4:
        flags.append("poor_readability")
    if signals["structural_quality"] < 0.4:
        flags.append("low_structure")

    return ContentQualityResult(
        score=round(composite, 4),
        signal_scores={k: round(v, 4) for k, v in signals.items()},
        flags=flags,
        text_length=len(text),
        word_count=word_count,
    )
