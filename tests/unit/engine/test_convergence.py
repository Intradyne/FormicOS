"""Wave 79 Track 2B: Diminishing returns detection tests."""

from __future__ import annotations

from formicos.engine.runner import (
    _detect_diminishing_returns,
    _trigram_jaccard,
)


class TestTrigramJaccard:
    def test_identical_strings(self) -> None:
        assert _trigram_jaccard("hello world", "hello world") == 1.0

    def test_completely_different(self) -> None:
        sim = _trigram_jaccard("aaaaaa", "zzzzzz")
        assert sim == 0.0

    def test_partial_overlap(self) -> None:
        sim = _trigram_jaccard("hello world", "hello earth")
        assert 0.0 < sim < 1.0

    def test_short_strings(self) -> None:
        assert _trigram_jaccard("ab", "cd") == 0.0  # too short

    def test_empty_strings(self) -> None:
        assert _trigram_jaccard("", "") == 0.0


class TestDiminishingReturns:
    def test_identical_summaries_detected(self) -> None:
        summaries = [
            "Agent wrote file src/main.py",
            "Agent wrote file src/main.py",
            "Agent wrote file src/main.py",
        ]
        assert _detect_diminishing_returns(summaries) is True

    def test_diverse_summaries_not_detected(self) -> None:
        summaries = [
            "Agent wrote file src/main.py",
            "Agent ran tests and they passed",
            "Agent committed the changes",
        ]
        assert _detect_diminishing_returns(summaries) is False

    def test_too_few_summaries(self) -> None:
        assert _detect_diminishing_returns(["one", "two"]) is False

    def test_empty_list(self) -> None:
        assert _detect_diminishing_returns([]) is False

    def test_custom_threshold(self) -> None:
        summaries = [
            "Agent read the file contents",
            "Agent read the file contents again",
            "Agent read the file contents once more",
        ]
        # With strict threshold these should pass
        assert _detect_diminishing_returns(summaries, threshold=0.95) is False

    def test_custom_window(self) -> None:
        summaries = [
            "different work here",
            "same output here",
            "same output here",
            "same output here",
            "same output here",
        ]
        # Window of 4 — last 4 are identical
        assert _detect_diminishing_returns(summaries, window=4) is True

    def test_only_checks_recent_window(self) -> None:
        summaries = [
            "old different work",
            "old different work two",
            "new repeating output",
            "new repeating output",
            "new repeating output",
        ]
        # Default window=3, last 3 are identical
        assert _detect_diminishing_returns(summaries) is True
