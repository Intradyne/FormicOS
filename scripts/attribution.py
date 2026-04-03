#!/usr/bin/env python3
"""Deterministic contributor attribution from git blame.

Computes surviving-line weights for the contributor revenue share pool.
Standalone script — does not import FormicOS runtime code.

Usage:
    python scripts/attribution.py \\
        --repo . \\
        --branch main \\
        --revenue 1250.00 \\
        --maintainer-floor 0.50 \\
        --min-payout 25.00 \\
        --ignore-revs .git-blame-ignore-revs \\
        --aliases .formicos/email-aliases.json \\
        --output reports/attribution-2026-Q2.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Maintainer identity (Intradyne) — receives the floor guarantee.
MAINTAINER_EMAIL = "intradyne@users.noreply.github.com"

# Directories to scan.
SOURCE_DIRS = ("src/", "frontend/src/", "config/", "addons/")


# ---------------------------------------------------------------------------
# Pure helpers (testable without git)
# ---------------------------------------------------------------------------


def load_aliases(path: Path | None) -> dict[str, str]:
    """Load email alias mapping. Returns empty dict if file missing."""
    if path is None or not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def is_whitespace_only(line: str) -> bool:
    """Return True if the line is empty or whitespace-only."""
    return line.strip() == ""


def aggregate_lines(
    blame_entries: list[dict[str, str]],
    aliases: dict[str, str],
) -> dict[str, int]:
    """Count surviving non-whitespace lines per canonical author email."""
    counts: dict[str, int] = {}
    for entry in blame_entries:
        if is_whitespace_only(entry.get("content", "")):
            continue
        email = entry.get("author-mail", "").strip("<>").lower()
        email = aliases.get(email, email)
        if not email:
            continue
        counts[email] = counts.get(email, 0) + 1
    return counts


def compute_shares(
    line_counts: dict[str, int],
    *,
    maintainer_email: str = MAINTAINER_EMAIL,
    maintainer_floor: float = 0.50,
) -> dict[str, float]:
    """Compute gross share percentages with maintainer floor applied.

    Returns {email: share} where shares sum to 1.0.
    """
    total = sum(line_counts.values())
    if total == 0:
        return {}

    # Raw proportions.
    raw: dict[str, float] = {
        email: count / total for email, count in line_counts.items()
    }

    maintainer_raw = raw.get(maintainer_email, 0.0)

    # If maintainer already above floor, return raw proportions.
    if maintainer_raw >= maintainer_floor:
        return raw

    # Apply floor: give maintainer the floor, distribute remaining pool
    # proportionally among non-maintainer contributors.
    remaining_pool = 1.0 - maintainer_floor
    non_maintainer_total = sum(
        v for k, v in raw.items() if k != maintainer_email
    )

    result: dict[str, float] = {maintainer_email: maintainer_floor}
    if non_maintainer_total > 0:
        for email, share in raw.items():
            if email != maintainer_email:
                result[email] = (share / non_maintainer_total) * remaining_pool
    return result


def compute_payouts(
    shares: dict[str, float],
    revenue: float,
    min_payout: float = 25.0,
) -> list[dict[str, object]]:
    """Compute per-contributor payout amounts.

    Returns list of contributor records with payout and eligibility info.
    """
    results = []
    for email, share in sorted(shares.items(), key=lambda x: -x[1]):
        amount = round(share * revenue, 2)
        results.append({
            "email": email,
            "share": round(share, 6),
            "gross_amount": amount,
            "eligible": amount >= min_payout,
            "note": "" if amount >= min_payout else f"below ${min_payout:.2f} threshold — accrued",
        })
    return results


# ---------------------------------------------------------------------------
# Git interaction
# ---------------------------------------------------------------------------


def run_git_blame(
    repo: Path,
    branch: str,
    paths: tuple[str, ...],
    ignore_revs: Path | None = None,
) -> list[dict[str, str]]:
    """Run git blame and parse line-porcelain output."""
    entries: list[dict[str, str]] = []

    for src_dir in paths:
        target = repo / src_dir
        if not target.exists():
            continue

        # Find tracked files in this directory.
        try:
            file_list = subprocess.check_output(
                ["git", "ls-files", src_dir],
                cwd=str(repo),
                text=True,
                encoding="utf-8",
            ).strip().splitlines()
        except subprocess.CalledProcessError:
            continue

        for filepath in file_list:
            cmd = ["git", "blame", "-w", "--line-porcelain", branch, "--", filepath]
            if ignore_revs and ignore_revs.exists():
                cmd.insert(3, f"--ignore-revs-file={ignore_revs}")
            try:
                output = subprocess.check_output(
                    cmd, cwd=str(repo), text=True, encoding="utf-8",
                    errors="replace", stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue

            current: dict[str, str] = {}
            for line in output.splitlines():
                if line.startswith("\t"):
                    current["content"] = line[1:]
                    entries.append(current)
                    current = {}
                elif " " in line:
                    key, _, value = line.partition(" ")
                    current[key] = value

    return entries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_report(
    *,
    repo: Path,
    branch: str,
    revenue: float,
    maintainer_floor: float,
    min_payout: float,
    ignore_revs: Path | None,
    aliases_path: Path | None,
) -> dict[str, object]:
    """Build the full attribution report."""
    aliases = load_aliases(aliases_path)
    blame_entries = run_git_blame(repo, branch, SOURCE_DIRS, ignore_revs)
    line_counts = aggregate_lines(blame_entries, aliases)
    shares = compute_shares(
        line_counts,
        maintainer_floor=maintainer_floor,
    )
    payouts = compute_payouts(shares, revenue, min_payout)

    total_lines = sum(line_counts.values())

    return {
        "branch": branch,
        "total_surviving_lines": total_lines,
        "revenue": revenue,
        "maintainer_floor": maintainer_floor,
        "min_payout": min_payout,
        "contributors": payouts,
        "line_counts": dict(sorted(line_counts.items(), key=lambda x: -x[1])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FormicOS contributor attribution")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root")
    parser.add_argument("--branch", default="main", help="Branch to blame")
    parser.add_argument("--revenue", type=float, required=True, help="Revenue pool ($)")
    parser.add_argument(
        "--maintainer-floor", type=float, default=0.50, help="Maintainer min share",
    )
    parser.add_argument(
        "--min-payout", type=float, default=25.00, help="Min payout threshold ($)",
    )
    parser.add_argument(
        "--ignore-revs", type=Path, default=None, help=".git-blame-ignore-revs path",
    )
    parser.add_argument("--aliases", type=Path, default=None, help="Email alias mapping JSON")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")

    args = parser.parse_args()

    report = build_report(
        repo=args.repo,
        branch=args.branch,
        revenue=args.revenue,
        maintainer_floor=args.maintainer_floor,
        min_payout=args.min_payout,
        ignore_revs=args.ignore_revs,
        aliases_path=args.aliases,
    )

    # Human-readable stdout
    print(f"\n{'='*60}")
    print(f"Attribution Report — {args.branch}")
    print(f"{'='*60}")
    print(f"Total surviving lines: {report['total_surviving_lines']}")
    print(f"Revenue pool: ${args.revenue:.2f}")
    print(f"Maintainer floor: {args.maintainer_floor:.0%}")
    print("\nContributors:")
    for c in report["contributors"]:  # type: ignore[union-attr]
        status = "ELIGIBLE" if c["eligible"] else "ACCRUED"
        print(f"  {c['email']:<40} {c['share']:.4%}  ${c['gross_amount']:>8.2f}  [{status}]")

    # JSON output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {args.output}")

    sys.exit(0)


if __name__ == "__main__":
    main()
