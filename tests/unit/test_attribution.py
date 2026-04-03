"""Tests for scripts/attribution.py — pure helper functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from attribution import (  # noqa: E402
    aggregate_lines,
    compute_payouts,
    compute_shares,
    is_whitespace_only,
    load_aliases,
)


class TestIsWhitespaceOnly:
    def test_empty(self) -> None:
        assert is_whitespace_only("")

    def test_spaces(self) -> None:
        assert is_whitespace_only("   ")

    def test_tabs(self) -> None:
        assert is_whitespace_only("\t\t")

    def test_content(self) -> None:
        assert not is_whitespace_only("  x  ")


class TestLoadAliases:
    def test_missing_file(self) -> None:
        assert load_aliases(Path("/nonexistent/aliases.json")) == {}

    def test_none_path(self) -> None:
        assert load_aliases(None) == {}

    def test_valid_file(self, tmp_path: Path) -> None:
        p = tmp_path / "aliases.json"
        p.write_text(json.dumps({"old@example.com": "new@example.com"}))
        result = load_aliases(p)
        assert result == {"old@example.com": "new@example.com"}


class TestAggregateLines:
    def test_counts_non_whitespace(self) -> None:
        entries = [
            {"author-mail": "<alice@example.com>", "content": "def foo():"},
            {"author-mail": "<alice@example.com>", "content": "    return 1"},
            {"author-mail": "<bob@example.com>", "content": "def bar():"},
            {"author-mail": "<alice@example.com>", "content": ""},  # whitespace
            {"author-mail": "<bob@example.com>", "content": "   "},  # whitespace
        ]
        counts = aggregate_lines(entries, {})
        assert counts == {"alice@example.com": 2, "bob@example.com": 1}

    def test_applies_aliases(self) -> None:
        entries = [
            {"author-mail": "<old@example.com>", "content": "code"},
        ]
        aliases = {"old@example.com": "new@example.com"}
        counts = aggregate_lines(entries, aliases)
        assert counts == {"new@example.com": 1}

    def test_empty_entries(self) -> None:
        assert aggregate_lines([], {}) == {}


class TestComputeShares:
    def test_maintainer_above_floor(self) -> None:
        counts = {"maintainer@x.com": 80, "contrib@y.com": 20}
        shares = compute_shares(
            counts, maintainer_email="maintainer@x.com", maintainer_floor=0.50,
        )
        assert abs(shares["maintainer@x.com"] - 0.80) < 1e-6
        assert abs(shares["contrib@y.com"] - 0.20) < 1e-6

    def test_maintainer_below_floor(self) -> None:
        counts = {"maintainer@x.com": 10, "contrib@y.com": 90}
        shares = compute_shares(
            counts, maintainer_email="maintainer@x.com", maintainer_floor=0.50,
        )
        assert abs(shares["maintainer@x.com"] - 0.50) < 1e-6
        assert abs(shares["contrib@y.com"] - 0.50) < 1e-6

    def test_multiple_contributors_below_floor(self) -> None:
        counts = {"maintainer@x.com": 10, "a@y.com": 45, "b@y.com": 45}
        shares = compute_shares(
            counts, maintainer_email="maintainer@x.com", maintainer_floor=0.50,
        )
        assert abs(shares["maintainer@x.com"] - 0.50) < 1e-6
        # a and b split the remaining 50% equally
        assert abs(shares["a@y.com"] - 0.25) < 1e-6
        assert abs(shares["b@y.com"] - 0.25) < 1e-6

    def test_empty_counts(self) -> None:
        assert compute_shares({}) == {}

    def test_shares_sum_to_one(self) -> None:
        counts = {"m@x.com": 5, "a@y.com": 30, "b@y.com": 65}
        shares = compute_shares(counts, maintainer_email="m@x.com", maintainer_floor=0.50)
        assert abs(sum(shares.values()) - 1.0) < 1e-6


class TestComputePayouts:
    def test_eligible_and_accrued(self) -> None:
        shares = {"alice@x.com": 0.80, "bob@y.com": 0.20}
        payouts = compute_payouts(shares, revenue=100.0, min_payout=25.0)
        alice = next(p for p in payouts if p["email"] == "alice@x.com")
        bob = next(p for p in payouts if p["email"] == "bob@y.com")
        assert alice["gross_amount"] == 80.0
        assert alice["eligible"] is True
        assert bob["gross_amount"] == 20.0
        assert bob["eligible"] is False
        assert "threshold" in str(bob["note"])

    def test_zero_revenue(self) -> None:
        shares = {"alice@x.com": 1.0}
        payouts = compute_payouts(shares, revenue=0.0)
        assert payouts[0]["gross_amount"] == 0.0
