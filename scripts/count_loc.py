#!/usr/bin/env python3
"""LOC counter for FormicOS constitutional budget tracking.

Counts non-blank, non-comment lines in the four runtime layers.
Constitutional limit: ≤15,000 LOC across core + engine + adapters + surface.
Frontend target: ≤5,000 LOC.
"""

from pathlib import Path


def count_python_loc(directory: Path) -> int:
    """Count non-blank, non-comment lines in all .py files."""
    total = 0
    for py_file in sorted(directory.rglob("*.py")):
        for line in py_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                total += 1
    return total


def count_ts_loc(directory: Path) -> int:
    """Count non-blank, non-comment lines in all .ts/.tsx files."""
    total = 0
    for ext in ("*.ts", "*.tsx"):
        for ts_file in sorted(directory.rglob(ext)):
            if "node_modules" in str(ts_file):
                continue
            for line in ts_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("//"):
                    total += 1
    return total


def main() -> None:
    root = Path("src/formicos")
    frontend = Path("frontend/src")

    layers = {
        "core": root / "core",
        "engine": root / "engine",
        "adapters": root / "adapters",
        "surface": root / "surface",
    }

    print("FormicOS LOC Budget\n" + "=" * 40)

    runtime_total = 0
    for name, path in layers.items():
        if path.exists():
            loc = count_python_loc(path)
            runtime_total += loc
            print(f"  {name + '/':12s} {loc:>6,} LOC")
        else:
            print(f"  {name + '/':12s}      0 LOC (not found)")

    print(f"  {'─' * 30}")
    print(f"  {'RUNTIME TOTAL':12s} {runtime_total:>6,} / 15,000 LOC")

    remaining = 15_000 - runtime_total
    pct = (runtime_total / 15_000) * 100
    print(f"  {'Headroom':12s} {remaining:>6,} LOC ({100 - pct:.1f}% remaining)")

    if frontend.exists():
        fe_loc = count_ts_loc(frontend)
        print(f"\n  {'frontend/':12s} {fe_loc:>6,} / 5,000 LOC (target)")

    if runtime_total > 12_000:
        print("\n  ⚠️  WARNING: Approaching 15K limit. Review before adding features.")
    if runtime_total > 15_000:
        print("\n  🚨 VIOLATION: Runtime exceeds 15,000 LOC constitutional limit!")


if __name__ == "__main__":
    main()
